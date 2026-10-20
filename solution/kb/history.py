"""History records: every fact read from page text, searched
with the question itself, so an answer gets the dated values of what it asks about even when its 16 search excerpts
miss the page that has them.

Records are rebuilt by code at the end of each ingest():
- a fact record per named fact (kb/facts): its values with publish dates and downloads, and, when the judge found a
  contradiction, the value judged current;
Table changes come from the changes index (kb/changes.py), as page text before and after.
When answering, two lookups fill the <history> block: the records that best match the question (BM25 and meaning
search, the same models as the chunk search), and the judged facts stated in the 16 excerpts. Each line says what
the download being answered from shows ("shown now"). Values from other downloads are listed only when the question
refers to another time (a date, "before", "changed", an as_of date): a question about now never sees them, so it
cannot repeat them. No Claude call.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np

from . import config
from .facts.book import FactBook
from .facts.extract import Fact, plain
from .facts.judge import iso, value_key
from .facts.notes import MATCH_CHARS, line as verdict_line
from .retrieval import Chunk
from .retrieval.bm25 import BM25Index
from .retrieval.embeddings import Embedder


# A question that refers to another time than now: it gets the values of other downloads too (deliberately broad).
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
# A year counts only after a time word ("in 2025", "as of June 2026"): on this site years also name products ("2025
# model-year vehicle", "2026 grant cycle").
TIME_REFERENCE = re.compile(r"\b(?:before|previous(?:ly)?|prior|used to|chang\w*|since|ago|earlier|former(?:ly)?|"
                            r"histor\w*|was|were|did|had|went|rose|fell|dropp\w*|rais\w*|lower\w*|increas\w*|"
                            r"decreas\w*|then|back in|at the time|as of|last (?:year|month|week|time)|"
                            r"(?:in|since|as of|during|before|after|until|by|from|through)\s+(?:(?:early|mid|late)[- ])?"
                            r"(?:19|20)\d\d|" + MONTHS + r")\b", re.I)


def refers_to_another_time(question: str, as_of) -> bool:
    return as_of is not None or bool(TIME_REFERENCE.search(question))


@dataclass
class Record:
    text: str                                       # what the question is matched against
    kind: str                                       # "fact" or "table"
    name: str                                       # shown in the history line
    seen: list[tuple[str, str, object, str]] = field(default_factory=list)  # (download, value shown, key, date)
    facts: list[Fact] = field(default_factory=list)                         # fact records: the facts behind them


def spans(snaps) -> str:
    """['01', '02', '03', '05'] -> '01-03, 05'."""
    out, start, prev = [], None, None
    for s in sorted(snaps):
        if start is not None and int(s) == int(prev) + 1:
            prev = s
            continue
        if start is not None:
            out.append(start if start == prev else f"{start}-{prev}")
        start = prev = s
    if start is not None:
        out.append(start if start == prev else f"{start}-{prev}")
    return ", ".join(out)


def fact_records(by_fact: dict[str, list[Fact]]) -> list[Record]:
    """One record per named fact, its wordings searchable."""
    out = []
    for name, facts in by_fact.items():
        wordings = Counter(f"{f.subject} {f.attribute}" for f in facts)
        rec = Record(text=" ".join([name, *wordings]), kind="fact", name=name, facts=facts)
        for f in facts:
            date = max((iso(d) for d in f.paragraph.dates.values()), default="")
            shown = f.value + (f" (for {f.refers_to})" if f.refers_to else "")
            for snaps in f.paragraph.seen.values():
                for snap in snaps:
                    rec.seen.append((snap, shown, (value_key(f.value), f.refers_to), date))
        out.append(rec)
    return out


def states(rec: Record, snap: str) -> list[dict]:
    """The record's distinct values seen up to download `snap`, the one shown latest first."""
    by: dict[object, dict] = {}
    for s, shown, key, date in rec.seen:
        if s <= snap:
            v = by.setdefault(key, {"snaps": set(), "dates": set(), "shown": shown})
            v["snaps"].add(s)
            if date:
                v["dates"].add(date)
    return sorted(by.values(), key=lambda v: (max(v["snaps"]), max(v["dates"], default="")), reverse=True)


def describe(v: dict, kind: str) -> str:
    return f"{v['shown']} (downloads {spans(v['snaps'])}" + (f", published {max(v['dates'])}" if v["dates"] else "") + ")"


def record_line(rec: Record, snap: str, timeline: bool, verdicts: dict) -> str | None:
    """What the record says as of download `snap`: the values shown in it, and with `timeline` those of others."""
    if rec.kind == "fact" and rec.name in verdicts:
        return verdict_line(verdicts[rec.name], snap, timeline)
    vs = states(rec, snap)
    if not vs:
        return None
    now = [v for v in vs if snap in v["snaps"]]
    earlier = [v for v in vs if snap not in v["snaps"]]
    parts = [("shown now: " + "; ".join(describe(v, rec.kind) for v in now[:4])) if now
             else f"no longer shown (last seen in download {max(max(v['snaps']) for v in vs)})"]
    if timeline and earlier:
        parts.append("earlier, no longer shown: " + "; ".join(describe(v, rec.kind) for v in earlier[:3]))
    return f"{rec.name}: " + " | ".join(parts)


class History:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self.records: list[Record] = []
        self.verdicts: dict[str, dict] = {}
        self.by_page: dict[str, list[Fact]] = {}
        self.bm25 = BM25Index([])
        self.vectors = None

    def rebuild(self, book: FactBook, wider=None) -> None:
        """Records from everything ingested so far (code only; new record texts are embedded once). With `wider`
        (kb.facts.wider.WiderFacts, config.HISTORY_NEW_WARNINGS) its judged facts and verdicts are added too."""
        facts = book.facts + (wider.warning_facts() if wider else [])
        by_fact: dict[str, list[Fact]] = defaultdict(list)
        for f in facts:
            by_fact[f.group].append(f)
        self.records = fact_records(dict(by_fact))
        self.verdicts = wider.verdicts if wider else book.verdicts
        self.by_page = defaultdict(list)
        for f in facts:
            for url in f.paragraph.seen:
                self.by_page[url].append(f)
        docs = [r.text for r in self.records]
        self.bm25 = BM25Index(docs)
        self.vectors = self.embedder.embed(docs) if docs else None
        self._fact_record = {r.name: r for r in self.records if r.kind == "fact"}

    def note(self, question: str, snap: str, hits: list[Chunk], timeline: bool) -> str:
        """The <history> lines as of download `snap`: the records that best match the question, then the judged
        facts stated in the excerpts."""
        known = [s for s in self.verdicts if s <= snap]
        verdicts = self.verdicts[max(known)] if known else {}
        lines: list[str] = []

        def add(rec: Record) -> None:
            text = record_line(rec, snap, timeline, verdicts)
            if text and text not in lines:
                lines.append(text)

        for i in self._ranked(question):
            if len(lines) == config.HISTORY_RECORDS:
                break
            add(self.records[i])
        excerpt_names: list[str] = []
        for c in hits:
            body = plain(c.body)
            for url in c.copies or [c.url]:
                for f in self.by_page.get(url, []):
                    if (f.group in verdicts and f.group not in excerpt_names
                            and plain(f.paragraph.text)[:MATCH_CHARS] in body):
                        excerpt_names.append(f.group)
        for name in excerpt_names[:config.HISTORY_EXCERPT_FACTS]:
            add(self._fact_record[name])
        return "\n".join(lines)

    def _ranked(self, question: str) -> list[int]:
        depth = config.CANDIDATES_PER_RANKER
        rankings = [self.bm25.rank(question)[:depth]]
        q = self.embedder.query(question)
        if q is not None and self.vectors is not None:
            rankings.append(list(np.argsort(-(self.vectors @ q))[:depth]))
        fused = Counter()
        for ranking in rankings:
            for rank, i in enumerate(ranking):
                fused[i] += 1 / (config.RRF_K + rank + 1)
        return [i for i, _ in fused.most_common()]
