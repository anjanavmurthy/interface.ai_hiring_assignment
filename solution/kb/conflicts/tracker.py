"""The table stages that run inside ingest(): s1 -> s2 -> s3, one snapshot at a time.

Each snapshot's pages are read as it arrives (s1), its tables are grouped into layouts together with everything seen
before (s2), and only layouts never seen before are sent to the LLM for their column roles (s3). The first snapshot
labels almost every layout; later ones only the few new layouts. The comparison stages (s4-s7) read `pages`,
`roles_of()` and `snap_dates` from here.
"""
from __future__ import annotations

from .. import config
from ..cleaning import is_listing_page
from ..llm import CachedLLM
from .s1_read_tables import labelling_tables, outline_page
from .s2_group_layouts import group_layouts, number_tables
from .s3_label_columns import label_columns, roles_by_header


class TableTracker:
    def __init__(self, llm: CachedLLM):
        self.llm = llm
        self.pages: list[dict] = []           # s1 reader 1: every page of every snapshot (for s4-s7)
        self.tables: list[dict] = []          # s1 reader 2: every table of every non-listing page (for s2-s3)
        self.labels: dict[str, dict] = {}     # layout key -> the LLM's answer for that layout (with its header)
        self.snap_dates: dict[str, str] = {}  # '01' -> '2026-05-12'

    def add_snapshot(self, snapshot_id: str, pages: list[tuple[str, str]]) -> None:
        """Read one snapshot's pages, given as (url, cleaned text) for every page, and label its new layouts."""
        snap = snapshot_id[:2]
        self.snap_dates[snap] = snapshot_id[3:13]
        for url, text in pages:
            self.pages.append(outline_page(snap, url, text))
            if not is_listing_page(url):
                self.tables += labelling_tables(snap, url, text)
        self.label_new_layouts()

    def label_new_layouts(self) -> None:
        """Send the layouts without column roles to the LLM; a layout whose requests fail stays unlabelled (its
        tables are not read) and is tried again with the next snapshot."""
        number_tables(self.tables)
        new = [lay for lay in group_layouts(self.tables) if lay["key"] not in self.labels]
        key_of = {lay["id"]: lay["key"] for lay in new}
        for answer in label_columns(new, self.llm, config.LABEL_LAYOUTS_PER_CALL, config.LLM_PARALLEL):
            self.labels[key_of[answer["id"]]] = answer

    def roles_of(self) -> dict[str, list[str]]:
        """{header key: column roles} for the labelled layouts whose tables are followed."""
        return roles_by_header(list(self.labels.values()))
