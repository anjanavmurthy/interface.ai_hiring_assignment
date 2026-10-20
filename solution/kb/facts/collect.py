"""Facts, step 1 (code): which text of a snapshot Claude reads for facts.

Pages of the WHOLE_PAGE_TYPES are sent whole the first time they are seen. When one changes in a later snapshot,
only its paragraphs never sent before go out, each with the whole section it sits in (its heading and the
paragraphs around it, as context). Every other page is read only in part: a paragraph that ties Dupaco to an
amount, rate or count, or holds a phone number or a dupaco.com address (site_rules), with its heading and the
paragraph before it as context. The "About Dupaco" paragraph printed under press releases is taken out of every
page, and each distinct wording is sent once. Tables are left out: the table stages (kb/conflicts) follow them.

A paragraph already sent is never sent again: the new snapshot and page are only recorded on it, so its facts carry
every place and time they were seen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..cleaning import detailed_page_type, header_date
from ..cleaning.site_rules import ABOUT_FOOTER, DUPACO_NUMBER, DUPACO_WEB_ADDRESS, PHONE_NUMBER

WHOLE_PAGE_TYPES = ("news", "product", "promo/landing", "rates", "about/contact", "community")
HEADING = re.compile(r"^#{1,6}\s")


@dataclass
class Paragraph:
    id: str                                                    # 'p123'
    text: str
    seen: dict[str, set[str]] = field(default_factory=dict)    # page url -> snapshots it was on that page
    dates: dict[str, str] = field(default_factory=dict)        # page url -> that page's publish date ('May 05, 2026')


@dataclass
class Document:
    """What one page (or the footer versions) contributes to an extraction request."""
    url: str                                   # the page, or 'footer' for the About-Dupaco versions
    article_date: str | None
    parts: list[tuple[str, Paragraph | None]]  # (text, paragraph to extract from | None for context only)


def paragraphs_of(text: str) -> list[str]:
    """The page's paragraphs, tables left out (the table stages read those)."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip() and not p.strip().startswith("|")]


def may_state_a_fact(paragraph: str) -> bool:
    """On a page read only in part: does this paragraph tie Dupaco to a number, or hold contact details?"""
    return bool(DUPACO_NUMBER.search(paragraph) or PHONE_NUMBER.search(paragraph)
                or DUPACO_WEB_ADDRESS.search(paragraph))


def heading_before(paras: list[str], i: int) -> str | None:
    return next((paras[k] for k in range(i - 1, -1, -1) if HEADING.match(paras[k])), None)


def sections(paras: list[str]) -> list[list[int]]:
    """Paragraph indexes grouped by section: each heading starts a new one."""
    out: list[list[int]] = [[]]
    for i, p in enumerate(paras):
        if HEADING.match(p) and out[-1]:
            out.append([])
        out[-1].append(i)
    return out


class Collector:
    def __init__(self):
        self.paragraphs: dict[str, Paragraph] = {}     # text -> Paragraph, over all pages and snapshots

    def _paragraph(self, text: str) -> tuple[Paragraph, bool]:
        """The paragraph for this text and whether it is new."""
        if text in self.paragraphs:
            return self.paragraphs[text], False
        p = self.paragraphs[text] = Paragraph(f"p{len(self.paragraphs) + 1}", text)
        return p, True

    def add_snapshot(self, snapshot_id: str, pages: list[tuple[str, str]]) -> list[Document]:
        """The documents to send for one snapshot, given (url, cleaned text) for every page."""
        snap = snapshot_id[:2]
        docs, new_footers = [], []
        for url, text in pages:
            whole = detailed_page_type(url) in WHOLE_PAGE_TYPES
            paras = paragraphs_of(text)
            date = header_date(text)
            if not whole:
                docs += self._part_of_page(snap, url, date, paras, new_footers)
                continue
            body, new = [], set()
            for i, t in enumerate(paras):
                p, is_new = self._paragraph(t)
                p.seen.setdefault(url, set()).add(snap)
                if date:
                    p.dates[url] = date
                if ABOUT_FOOTER.match(t):
                    if is_new:
                        new_footers.append(p)
                    continue
                body.append(i)
                if is_new:
                    new.add(i)
            if not new:
                continue
            first_time = len(new) == len(body)
            keep = [i for sec in sections(paras) if first_time or new & set(sec) for i in sec if i in body]
            docs.append(Document(url, date, [(paras[i], self.paragraphs[paras[i]] if i in new else None)
                                             for i in keep]))
        if new_footers:
            docs.append(Document("footer", None, [(p.text, p) for p in new_footers]))
        return docs

    def _part_of_page(self, snap: str, url: str, date: str | None, paras: list[str],
                      new_footers: list[Paragraph]) -> list[Document]:
        """A page read only in part: its footer copy and the paragraphs that may state a fact, with context."""
        parts: list[tuple[str, Paragraph | None]] = []
        for i, t in enumerate(paras):
            footer = bool(ABOUT_FOOTER.match(t))
            if not footer and not may_state_a_fact(t):
                continue
            p, is_new = self._paragraph(t)
            p.seen.setdefault(url, set()).add(snap)
            if date:
                p.dates[url] = date
            if footer:
                if is_new:
                    new_footers.append(p)
            elif is_new:
                context = [c for c in (heading_before(paras, i), paras[i - 1] if i else None) if c and c != t]
                parts += [(c, None) for c in dict.fromkeys(context) if not parts or parts[-1][0] != c] + [(t, p)]
        return [Document(url, date, parts)] if parts else []
