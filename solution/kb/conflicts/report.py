"""The contradictions in the scorer's shape: Conflict(topic, values, sources, resolution, reason).

Two kinds go in: table conflicts (s7 records: the judge's verdict on table cells) and fact conflicts (kb/facts
step 5: the judge's verdict on facts read from page text). Values are shown as written, without glued footnote
digits ("1.23% APR4" -> "1.23% APR"); the value to tell a member today comes first. Each value keeps a few of the
pages that state it, with the newest download it appeared in and the row or sentence as the quote.

A table conflict lists only the values that disagree: those shown together in the latest download where pages
disagree, or, for a value changed on a page, the value before the last change and the value after it. A cell's
earlier values that nobody contradicts are left out.
"""
from __future__ import annotations

from contract import Conflict, Source

from ..cleaning.page_info import SITE
from ..facts.judge import Verdict, sentence
from .s1_read_tables import plain
from .table_text import norm_value

SOURCES_PER_VALUE = 3


def shown(value: str) -> str:
    return plain(value).strip()


def disagreeing(record: dict) -> list[dict]:
    """The observations of the values in conflict: the latest download where the cells show different values, or
    (a change over time) the last two distinct values in the order they were seen."""
    seen = record["seen"]
    if record["same_snapshot"]:
        return [o for o in seen if o["snap"] == max(record["same_snapshot"])]
    order = []                                             # distinct values in the order they first appear
    for o in sorted(seen, key=lambda o: o["snap"]):
        if not order or order[-1] != norm_value(o["value"]):
            order.append(norm_value(o["value"]))
    last_two = set(order[-2:])
    return [o for o in seen if norm_value(o["value"]) in last_two]


def table_conflict(record: dict, snapshot_ids: dict[str, str]) -> Conflict:
    """One s7 record: the values that disagree, each with the pages that state it."""
    by_value: dict[str, dict[str, dict]] = {}              # value as shown -> page -> its newest observation
    spelling: dict[str, str] = {}                          # one spelling per value ("1.23%" and "1.23% APR" are one)
    for o in disagreeing(record):
        v = spelling.setdefault(norm_value(o["value"]), shown(o["value"]))
        pages = by_value.setdefault(v, {})
        if o["page"] not in pages or o["snap"] > pages[o["page"]]["snap"]:
            pages[o["page"]] = o
    resolution = spelling.get(norm_value(record["correct_value"]), shown(record["correct_value"]))
    values = sorted(by_value, key=lambda v: v != resolution)
    sources = [Source(url=SITE + o["page"], snapshot_id=snapshot_ids.get(o["snap"], o["snap"]), quote=o["row"])
               for v in values for o in sorted(by_value[v].values(), key=lambda o: o["snap"], reverse=True)
               [:SOURCES_PER_VALUE]]
    topic = " ".join(x for x in (record["title"], record["label"], record["column"]) if x)
    return Conflict(topic=topic, values=values, sources=sources, resolution=resolution, reason=record["why"])


def fact_conflict(v: Verdict, snapshot_ids: dict[str, str]) -> Conflict:
    """One judged fact: its competing values, each with a few of the pages that state it."""
    values = sorted(v.values, key=lambda x: x != v.correct_value)
    sources = []
    for value in values:
        newest_first = sorted(((max(snaps), url, f) for f in v.values[value] for url, snaps in f.paragraph.seen.items()),
                              key=lambda x: x[0], reverse=True)
        pages: dict[str, Source] = {}
        for snap, url, f in newest_first:
            if url not in pages and len(pages) < SOURCES_PER_VALUE:
                pages[url] = Source(url=url, snapshot_id=snapshot_ids.get(snap, snap), quote=sentence(f))
        sources += pages.values()
    return Conflict(topic=v.name.replace(" | ", " "), values=[shown(x) for x in values], sources=sources,
                    resolution=shown(v.correct_value), reason=v.why)
