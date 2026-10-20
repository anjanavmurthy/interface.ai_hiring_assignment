"""Facts from more page text, for conflicts only (config.FACTS_READ_MORE): a second pass after the FactBook.

The FactBook reads what it always read and feeds the answers; nothing here changes it. This second pass runs after
it in each ingest() and only reads from it:

1. it records every paragraph of every page with the pages and downloads it appears on, so a paragraph read in a
   later download still carries its whole history;
2. on the pages read in part, it picks the paragraphs the FactBook did not read that have a figure that can go out of
   date,
   in which Dupaco speaks for itself outside a quotation, or that name a known product or subject (the product cells
   of this download's tables and the subjects of the facts found so far, without names too short or too common);
   only paragraphs of config.READ_MORE_MIN_WORDS words or more;
3. it extracts their facts in requests of its own (config.FACTS_MORE_MODEL), so the FactBook's requests stay as they
   were;
4. catch-up (config.FACTS_CATCHUP): it reads this download's still-unread paragraphs that name a subject first found
   in this download;
5. it names the new facts with the FactBook's names as the known names, in batches when a type is large; the
   FactBook's names are never changed;
6. it judges again, for conflicts only, the facts whose set of values the new text changed.

`verdicts` (download -> fact name -> Verdict) is the FactBook's verdicts with the facts judged again replaced;
conflicts() reads it. `facts` holds the facts this pass found.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .. import config
from ..cleaning import detailed_page_type, header_date
from ..cleaning.site_rules import ABOUT_FOOTER, CHANGEABLE_FIGURE, DUPACO_SPEAKS, QUOTATION
from ..conflicts.s1_read_tables import cells
from ..conflicts.table_text import clean, header_key
from ..llm import CachedLLM
from .book import FactBook
from .collect import HEADING, WHOLE_PAGE_TYPES, Document, Paragraph, heading_before, paragraphs_of
from .extract import Fact, extract
from .group import Grouper, key_of
from .judge import Verdict, candidates, judge_facts, value_key

DUPACO_PREFIX = re.compile(r"^(?:the\s+)?dupaco(?:\s+community)?(?:\s+credit\s+union)?(?:'s|’s)?\s+", re.I)


def long_enough(paragraph: str) -> bool:
    return len(paragraph.split()) >= config.READ_MORE_MIN_WORDS


def worth_reading(paragraph: str) -> bool:
    """A figure that can go out of date, or Dupaco speaking for itself outside a quotation."""
    return long_enough(paragraph) and bool(CHANGEABLE_FIGURE.search(paragraph)
                                           or DUPACO_SPEAKS.search(QUOTATION.sub(" ", paragraph)))


def proper_name(subject: str) -> str:
    """A subject as it is looked for in text: without a leading 'Dupaco('s)', single spaces, case kept."""
    return re.sub(r"\s+", " ", DUPACO_PREFIX.sub("", clean(subject))).strip(" .:*")


class Names:
    """Known names, looked for as whole words with their case: the site writes a product, programme, branch or
    person's name capitalised ('Holiday Club'), so a name matched with its case is not a generic phrase."""

    def __init__(self, names: set[str]):
        self.names = names
        alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        self.pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)") if names else None

    def found_in(self, text: str) -> set[str]:
        return {m.group(0) for m in self.pattern.finditer(text)} if self.pattern else set()


def usable(names: set[str], paragraphs: list[str]) -> set[str]:
    """Names that can point at a fact: long enough, capitalised (a name, not a generic phrase), and not too common:
    one found in more than config.KNOWN_NAME_MAX_SHARE of the paragraphs names nothing in particular."""
    names = {n for n in names if len(n) >= config.KNOWN_NAME_MIN_CHARS and re.search(r"[A-Z]", n)}
    counts: dict[str, int] = defaultdict(int)
    finder = Names(names)
    for p in paragraphs:
        for n in finder.found_in(p):
            counts[n] += 1
    limit = config.KNOWN_NAME_MAX_SHARE * max(len(paragraphs), 1)
    return {n for n in names if counts[n] <= limit}


def table_products(tracker, snap: str) -> set[str]:
    """Product names in this download's tables, from the column labels (stage s3): the product cells, or the table's
    title or section when the label says the product comes from there."""
    labels = {header_key(cells(lab["header"])): lab for lab in tracker.labels.values()
              if lab.get("header") and lab.get("kind") in config.TRACKED_TABLE_KINDS}
    out = set()
    for t in tracker.tables:
        lab = labels.get(header_key(cells(t["header"]))) if t["snap"] == snap and t["header"] else None
        if lab is None:
            continue
        product = [c["index"] for c in lab["columns"] if c["role"] == "product"]
        if product:
            for row in t["rows"]:
                rc = cells(row)
                out.update(clean(rc[i]) for i in product if i < len(rc))
        elif lab.get("product_source") == "title" and t["title"]:
            out.add(clean(t["title"]))
        elif lab.get("product_source") == "section" and t["section"]:
            out.add(clean(t["section"].split(" > ")[-1]))
    return {proper_name(n) for n in out if n}


class WiderFacts:
    """The second pass over page text: its facts and verdicts, for conflicts()."""

    def __init__(self, extract_llm: CachedLLM, group_llm: CachedLLM, judge_llm: CachedLLM):
        self.extract_llm, self.judge_llm = extract_llm, judge_llm
        self.grouper = Grouper(group_llm, batch_over=config.NAMING_BATCH_OVER)
        self.own_names: dict = {}                              # pair -> name, for pairs the FactBook has not named
        self.seen: dict[str, dict[str, set[str]]] = {}         # paragraph -> page -> downloads it is on
        self.dates: dict[str, dict[str, str]] = {}             # paragraph -> page -> that page's publish date
        self.paragraphs: dict[str, Paragraph] = {}             # paragraphs this pass sent to Claude
        self.facts: list[Fact] = []
        self.verdicts: dict[str, dict[str, Verdict]] = {}      # download -> fact name -> verdict (for conflicts)
        self._judged: dict[str, frozenset[str]] = {}           # fact name -> the values this pass last judged
        self._latest: dict[str, Verdict | None] = {}           # fact name -> this pass's latest verdict (None: no
                                                               # contradiction)

    def add_snapshot(self, snapshot_id: str, pages: list[tuple[str, str]], book: FactBook, book_new: list[Fact],
                     tracker) -> list[Fact]:
        """Read one download after the FactBook did (book_new: the facts it added); returns the facts added here."""
        snap = snapshot_id[:2]
        by_page = []
        for url, text in pages:
            paras, date = paragraphs_of(text), header_date(text)
            by_page.append((url, paras, date))
            for t in paras:
                self.seen.setdefault(t, {}).setdefault(url, set()).add(snap)
                if date:
                    self.dates.setdefault(t, {})[url] = date
        distinct = list(dict.fromkeys(t for _, paras, _ in by_page for t in paras))
        just_found = {id(f) for f in book_new}
        before = {proper_name(f.subject) for f in book.facts + self.facts if id(f) not in just_found}
        known = Names(usable(table_products(tracker, snap) | before, distinct))
        docs = self._select(by_page, book,
                            lambda t: worth_reading(t) or (long_enough(t) and bool(known.found_in(t))))
        new, _ = extract(docs, self.extract_llm)
        if config.FACTS_CATCHUP:
            first_found = {proper_name(f.subject) for f in book_new + new} - before - known.names
            later = Names(usable(first_found, distinct))
            if later.names:
                more, _ = extract(self._select(by_page, book, lambda t: long_enough(t) and bool(later.found_in(t))),
                                  self.extract_llm)
                new += more
        self._name(book, new)
        self.facts += new
        self._judge(snap, book)
        return new

    def _select(self, by_page, book: FactBook, rule) -> list[Document]:
        """Documents of the paragraphs on pages read in part that neither the FactBook nor this pass read yet and that
        pass `rule`, each with its heading and the paragraph before it as context."""
        docs = []
        for url, paras, date in by_page:
            if detailed_page_type(url) in WHOLE_PAGE_TYPES:
                continue
            parts: list[tuple[str, Paragraph | None]] = []
            for i, t in enumerate(paras):
                if (HEADING.match(t) or ABOUT_FOOTER.match(t) or t in book.collector.paragraphs
                        or t in self.paragraphs or not rule(t)):
                    continue
                p = self.paragraphs[t] = Paragraph(f"q{len(self.paragraphs) + 1}", t, self.seen[t],
                                                   self.dates.setdefault(t, {}))
                context = [c for c in (heading_before(paras, i), paras[i - 1] if i else None) if c and c != t]
                parts += [(c, None) for c in dict.fromkeys(context) if not parts or parts[-1][0] != c] + [(t, p)]
            if parts:
                docs.append(Document(url, date, parts))
        return docs

    def _name(self, book: FactBook, new: list[Fact]) -> None:
        """Name the new facts; the FactBook's names come first and are known names, never renamed."""
        self.grouper.name_of = {**self.own_names, **book.grouper.name_of}
        self.grouper.add(new)
        self.own_names.update({k: v for k, v in self.grouper.name_of.items() if k not in book.grouper.name_of})
        names = {**self.own_names, **book.grouper.name_of}
        for f in self.facts + new:                       # a pair the FactBook named later takes the FactBook's name
            f.group = names[key_of(f)]

    def by_fact(self, book: FactBook) -> dict[str, list[Fact]]:
        """Every fact's values from the FactBook and this pass: name -> the facts that state it."""
        out: dict[str, list[Fact]] = defaultdict(list)
        for f in book.facts + self.facts:
            out[f.group].append(f)
        return dict(out)

    def _judge(self, snap: str, book: FactBook) -> None:
        """Judge the facts whose values the new text changed; the rest keep the FactBook's verdict."""
        book_only = book.by_fact()
        combined = self.by_fact(book)

        def values(facts) -> frozenset[str]:
            return frozenset(value_key(f.value) for f in facts)

        todo = [(name, vals) for name, vals in candidates(combined)
                if values(combined[name]) != values(book_only.get(name, []))
                and self._judged.get(name) != values(combined[name])]
        found, answered = judge_facts(todo, self.judge_llm, book.snap_dates)
        for name, _ in todo:
            if name in answered:                    # a failed request leaves the earlier verdict in place
                self._judged[name] = values(combined[name])
                self._latest[name] = None
        self._latest.update({v.name: v for v in found})
        merged = dict(book.verdicts.get(snap, {}))
        for name in self._judged:
            if values(combined.get(name, [])) != values(book_only.get(name, [])):
                merged.pop(name, None)
                if self._latest.get(name):
                    merged[name] = self._latest[name]
        self.verdicts[snap] = merged

    def warning_facts(self) -> list[Fact]:
        """This pass's facts whose name has a verdict in some download (config.HISTORY_NEW_WARNINGS)."""
        judged = {name for vs in self.verdicts.values() for name in vs}
        return [f for f in self.facts if f.group in judged]
