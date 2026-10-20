"""Stage 5 - choose which tables the judge compares together (code only).

Two groups look alike when they have the same customer type and at least SAME_ROWS_MIN of the smaller table's row
names are alike (exact, or at least ROW_NAME_SIMILAR similar). Rule E (decided by the user): tables whose row names
are all bare numbers only look alike when their column names are the same. Look-alike groups are joined into one
comparison set. A group alone is still judged when its values change between downloads or it has two rows with the
same name and different values. Personal and business tables are never compared.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .. import config
from .s4_track_tables import overlap
from .table_text import norm_value

OFFICIAL = {"rates", "product"}       # page types whose tables are listed first in a comparison set


def look_alike(a: dict, b: dict) -> bool:
    """Shown together: same customer type, rule E, enough row names alike."""
    if a["seg"] != b["seg"]:
        return False
    bare = [all(re.fullmatch(r"\d+( \(\d+\))?", k) for k in v["names"]) for v in (a, b)]
    if any(bare) and a["header"] != b["header"]:
        return False
    return overlap(a, b) >= config.SAME_ROWS_MIN


def official(g: dict) -> bool:
    return any(i["type"] in OFFICIAL for m in g["members"] for i in m["by_snap"].values())


def rows_of(g: dict) -> dict:
    """{row name: {column index: {snap: raw value}}} - rows matched only by their exact name."""
    out = defaultdict(lambda: defaultdict(dict))
    for s, v in sorted(g["timeline"].items()):
        rows = v["instances"][0]["rows"]
        for name, row in zip(v["names"], rows):
            for j in v["value_cols"]:
                if j < len(row):
                    out[name][j][s] = row[j]
    return out


def changes_over_time(g: dict) -> bool:
    return any(len({norm_value(x) for x in tl.values()}) > 1 for cols in rows_of(g).values() for tl in cols.values())


def duplicate_rows_differ(g: dict) -> bool:
    """Two rows with the same name ('A' and 'A (2)') whose values differ, in any download."""
    for v in g["timeline"].values():
        base = defaultdict(set)
        for name, row in zip(v["names"], v["instances"][0]["rows"]):
            base[re.sub(r" \(\d+\)$", "", name)].add(tuple(norm_value(row[j]) for j in v["value_cols"] if j < len(row)))
        if any(len(x) > 1 for x in base.values()):
            return True
    return False


def comparison_sets(gs: list[dict]) -> list[list[dict]]:
    """Look-alike groups joined together (union-find), official pages first; plus groups alone that change over
    time or have duplicate rows that differ. Each set becomes one comparison request to the judge."""
    parent = {g["id"]: g["id"] for g in gs}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for i, a in enumerate(gs):
        for b in gs[i + 1:]:
            if a["seg"] == b["seg"] and any(look_alike(a["timeline"][s], b["timeline"][s])
                                            for s in set(a["timeline"]) & set(b["timeline"])):
                parent[find(a["id"])] = find(b["id"])
    components = defaultdict(list)
    for g in gs:
        components[find(g["id"])].append(g)
    out = []
    for c in components.values():
        if len(c) > 1 or changes_over_time(c[0]) or duplicate_rows_differ(c[0]):
            out.append(sorted(c, key=lambda g: (not official(g), -len(g["pages"]), min(g["pages"]))))
    return out
