"""The unit of retrieval: a piece of one page, small enough to give Claude many of them per question."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chunk:
    url: str                     # the page this text came from
    label: str                   # "[Source: <url> | <page type> | fetched ... | published ... | effective ...]"
    page_type: str               # "rates", "product", "news", ... (see cleaning.site_rules.PAGE_TYPES)
    crumbs: str                  # "Page title > heading > subheading" - where in the page the text sits
    body: str                    # the text itself (tables kept whole, with their title line)
    published: str | None = None             # the page's article date, if it has one ("April 06, 2026")
    effective: list[str] = field(default_factory=list)   # "Rates are effective as of ..." dates in the body
    copies: list[str] = field(default_factory=list)      # every page in the snapshot with this exact body,
                                                          # official pages first (filled by SnapshotIndex)

    def search_text(self) -> str:
        """What the search indexes: headings + body, so a table is found by the heading above it too."""
        return self.crumbs + "\n" + self.body
