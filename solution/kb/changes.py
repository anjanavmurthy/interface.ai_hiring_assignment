"""The changes index: what changed on the site between downloads, page section by page section (code only).

At each ingest(), every page is split into sections (a heading and the paragraphs and tables under it) and compared
with the same page's sections in the previous download. A section whose content changed becomes an entry: the page,
the section, the two downloads, and the paragraphs or tables that were removed (before) and added (after). Blog and
listing pages are left out: their changes are widgets, author lines and reworded advice, not facts that change.

Questions that refer to another time (kb.history.refers_to_another_time) get the entries that best match them, up
to the download being answered from, so "what did it pay before" or "what was it in May" sees the page text of both
times. Search is BM25 over the page, section and text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import config
from .cleaning import detailed_page_type, is_listing_page, site_path
from .retrieval.bm25 import BM25Index

HEADING = re.compile(r"^#{1,6}\s")
SKIPPED_PAGE_TYPES = ("article",)


@dataclass
class Change:
    page: str
    section: str
    before_download: str
    after_download: str
    before: list[str]              # paragraphs / tables that were removed
    after: list[str]               # paragraphs / tables that were added

    def text(self) -> str:
        return " ".join([self.page, self.section, *self.before, *self.after])

    def describe(self) -> str:
        def side(parts: list[str]) -> str:
            joined = " / ".join(parts) or "(nothing)"
            return joined if len(joined) <= config.CHANGE_SIDE_CHARS else joined[:config.CHANGE_SIDE_CHARS] + " ..."
        return (f"{site_path(self.page)} [{self.section}], download {self.before_download} -> {self.after_download}:\n"
                f"  before: {side(self.before)}\n  after: {side(self.after)}")


def sections(text: str) -> dict[str, list[str]]:
    """Heading -> the paragraphs and tables under it (the part before the first heading is '(top)')."""
    out: dict[str, list[str]] = {}
    head = "(top)"
    for para in (p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()):
        if HEADING.match(para):
            head = para.lstrip("# ").strip()
            out.setdefault(head, [])
        else:
            out.setdefault(head, []).append(para)
    return out


class ChangeLog:
    def __init__(self):
        self.changes: list[Change] = []
        self._previous: dict[str, dict[str, list[str]]] = {}     # page -> its sections in the last download
        self._previous_snap = ""
        self.bm25 = BM25Index([])

    def add_snapshot(self, snapshot_id: str, pages: list[tuple[str, str]]) -> None:
        """Compare one download's pages, given as (url, cleaned text), with the previous download's."""
        snap = snapshot_id[:2]
        current = {url: sections(text) for url, text in pages
                   if not is_listing_page(url) and detailed_page_type(url) not in SKIPPED_PAGE_TYPES}
        for url, secs in current.items():
            old_secs = self._previous.get(url)
            if old_secs is None:
                continue
            for head, paras in secs.items():
                old = old_secs.get(head)
                if old is None or old == paras:
                    continue
                before = [p for p in old if p not in paras]
                after = [p for p in paras if p not in old]
                if before or after:
                    self.changes.append(Change(url, head, self._previous_snap, snap, before, after))
        self._previous, self._previous_snap = current, snap
        self.bm25 = BM25Index([c.text() for c in self.changes])

    def lines(self, question: str, snap: str) -> str:
        """The changes that best match the question, seen up to download `snap`."""
        out = []
        for i in self.bm25.rank(question):
            if self.changes[i].after_download <= snap:
                out.append(self.changes[i].describe())
            if len(out) == config.CHANGES_PER_QUESTION:
                break
        return "\n".join(out)
