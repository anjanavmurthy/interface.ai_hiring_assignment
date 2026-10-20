"""Facts, used when answering: how a judged fact is written in the <history> block (kb/history.py finds which).

The value judged current comes first, then the older values that pages still show, each with its latest publish
date and download, counting only downloads up to the one being answered from.
"""
from __future__ import annotations

from .extract import Fact
from .judge import Verdict, iso

MATCH_CHARS = 80               # how much of a paragraph's start must be in an excerpt for its facts to count


def when(facts: list[Fact], snap: str) -> str:
    """Latest publish date and download (up to the one being answered from) of the pages stating a value."""
    dates = [iso(d) for f in facts for d in f.paragraph.dates.values()]
    snaps = [s for f in facts for ss in f.paragraph.seen.values() for s in ss if s <= snap]
    return ", ".join(x for x in (f"published {max(dates)}" if dates else "",
                                 f"last seen in download {max(snaps)}" if snaps else "") if x)


def line(v: Verdict, snap: str, timeline: bool = True) -> str:
    """'name: current value (when); outdated values some pages still show: value (when); ...'. Without `timeline` (a
    question about now) only the current value is given."""
    current = f"{v.name}: {v.correct_value} is current ({when(v.values.get(v.correct_value, []), snap)})"
    if not timeline:                      # a question about now: the current value only
        return current
    older = [f"{x} ({when(fs, snap)})" for x, fs in v.values.items() if x != v.correct_value]
    return current + "; outdated values some pages still show: " + "; ".join(older)
