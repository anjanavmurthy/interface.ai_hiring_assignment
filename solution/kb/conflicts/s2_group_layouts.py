"""Stage 2 - group tables that share a header row into "layouts" (code only).

A layout is one header row, compared without case, footnote markers and markdown ('Annual Percentage Yield (APY)1'
and '(APY)2' are the same layout). Tables without a header row are grouped by their number of columns. The LLM in
stage 3 then labels each layout's columns once, and the label holds for every table with that header.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .s1_read_tables import cells, plain

EXAMPLE_ROWS = 4            # example rows shown to the LLM per layout


def layout_key(table: dict) -> str:
    if table["header"]:
        # a lone trailing digit in a header cell is a footnote marker too: '(As Low As) 1' = '(As Low As)1'
        return "H: " + " | ".join(re.sub(r"\s+\d{1,2}$", "", re.sub(r"\s+", " ", plain(c).lower()))
                                  for c in cells(table["header"]))
    return f"no header, {len(cells(table['rows'][0]))} columns"


def number_tables(tables: list[dict]) -> None:
    """Give every table instance an id 't00000', 't00001', ... in reading order."""
    for k, t in enumerate(tables):
        t["id"] = f"t{k:05d}"


def group_layouts(tables: list[dict]) -> list[dict]:
    """Layouts, most rows first, ids 'L001', 'L002', ...: header, how many tables/rows/pages use it, page types,
    the most common titles, and an example from the newest download that has it."""
    groups = defaultdict(list)
    for t in tables:
        groups[layout_key(t)].append(t)
    layouts = []
    for key, ts in sorted(groups.items(), key=lambda kv: -sum(len(t["rows"]) for t in kv[1])):
        newest = max(t["snap"] for t in ts)
        ex = next(t for t in ts if t["snap"] == newest)
        layouts.append({"key": key, "header": ex["header"], "tables": len(ts), "rows": sum(len(t["rows"]) for t in ts),
                        "pages": sorted({t["page"] for t in ts}),
                        "page_types": dict(Counter(t["type"] for t in ts).most_common()),
                        "titles": [x for x, _ in Counter(t["title"] for t in ts).most_common(8)],
                        "example": {"snap": ex["snap"], "page": ex["page"], "title": ex["title"],
                                    "section": ex["section"], "rows": ex["rows"][:EXAMPLE_ROWS]},
                        "table_ids": [t["id"] for t in ts]})
    for k, lay in enumerate(layouts, 1):
        lay["id"] = f"L{k:03d}"
    return layouts
