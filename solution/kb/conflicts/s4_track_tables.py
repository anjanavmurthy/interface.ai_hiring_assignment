"""Stage 4 - follow every table through the downloads, and find pages that always show the same table (code only).

  versions    identical tables in one download (same customer type, title and values once number formatting is
              ignored) are one version, listing every page that shows it
  histories   each page's table is followed from download to download: same page, same customer type, same number
              of columns and at least SAME_ROWS_MIN of row names alike (titles may change; they only break ties)
  groups      histories on different pages that show the identical table in every download they share

Row names and value columns come only from the column roles of stage 3: a row is named by its product, condition
and measure-label cells, and its value columns are compared. A table whose header has no roles or no value column is
skipped, and so is a row whose name comes out empty - guessing from the cells would merge tiers whose condition is an
amount (such as "$9,000+") into one name.
"""
from __future__ import annotations

import difflib
import re
from collections import defaultdict

from .. import config
from .table_text import clean, header_key, norm_value

EFFECTIVE = re.compile(r"effective(?:\s+as\s+of)?\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", re.I)


# --- row names and value columns ---------------------------------------------------------------------------
NAME_ROLES = ("product", "condition", "measure label")


def row_name(row: list[str], roles: list[str]) -> str:
    """The row's name: its product, condition and measure-label cells ('2024-27 Model Year | 60 Months'), or ''."""
    return " | ".join(clean(x) for x, r in zip(row, roles) if r in NAME_ROLES and clean(x))


def value_columns(roles: list[str]) -> list[int]:
    """The columns compared: the roles' value columns."""
    return [j for j, r in enumerate(roles) if r == "value"]


def title_of(above: str, heading: str) -> str:
    """Shown title: the line above the table, or the nearest heading when that line is not a title."""
    t = clean(above)
    if not t or len(t) > config.TITLE_MAX_CHARS or re.search(r"[.?!:]$|^[-•*]|[.?!]\s", t):
        return clean(heading)
    return t


def unique(names: list[str]) -> list[str]:
    """Repeated row names get a counter: ['A', 'B', 'A'] -> ['A', 'B', 'A (2)']."""
    seen, out = defaultdict(int), []
    for n in names:
        seen[n] += 1
        out.append(n if seen[n] == 1 else f"{n} ({seen[n]})")
    return out


# --- how alike two tables' rows are (used to follow a table over time and, in s5, to pick comparisons) --------
def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def pair_rows(a: dict, b: dict) -> list[tuple[str, str]]:
    """Row names of a and b that look alike (exact first, then the most similar remaining name). Used only to decide
    which tables to show together and to follow a page's table through time - never to merge rows for the judge."""
    pairs = [(k, k) for k in a["names"] if k in b["names"]]
    rest_b = [k for k in b["names"] if k not in a["names"]]
    for k in [k for k in a["names"] if k not in b["names"]]:
        best = max(rest_b, key=lambda x: similar(k, x), default=None)
        if best is not None and similar(k, best) >= config.ROW_NAME_SIMILAR:
            pairs.append((k, best))
            rest_b.remove(best)
    return pairs


def overlap(a: dict, b: dict) -> float:
    """Share of the smaller table's distinct row names that have a look-alike in the other table."""
    return len(pair_rows(a, b)) / min(len(set(a["names"])), len(set(b["names"])))


# --- the three steps --------------------------------------------------------------------------------------------
def read_versions(pages: list[dict], roles_of: dict[str, list[str]]) -> tuple[list[dict], list[dict]]:
    """(instances, versions). An instance is one table on one page in one download; a version is the set of
    identical instances in one download."""
    versions, instances = {}, []
    for p in pages:
        for si, s in enumerate(p["sections"]):
            heading = s["path"][-1] if s["path"] else ""
            eff = next((m[1] for x in s["numbers"] for m in [EFFECTIVE.search(x)] if m), None)
            for ti, t in enumerate(s["tables"]):
                roles = roles_of.get(header_key(t["header"]))
                if not roles or not value_columns(roles):          # no column roles: the table can't be read
                    continue
                rows = [r for r in t["cells"] if r and row_name(r, roles)]
                if not rows:
                    continue
                title, header = title_of(t["above"], heading), [clean(h) for h in t["header"]]
                text = " ".join([p["page"], title, heading, *header, *(clean(r[0]) for r in rows)])
                seg = "business" if re.search(r"business", text, re.I) else "personal"   # customer type
                key = (p["snap"], seg, title, tuple(tuple(norm_value(x) for x in r) for r in rows))
                v = versions.setdefault(key, {"snap": p["snap"], "seg": seg, "title": title, "header": header,
                                              "ncol": len(header), "names": unique([row_name(r, roles) for r in rows]),
                                              "value_cols": value_columns(roles),
                                              "pages": set(), "instances": []})
                inst = {"snap": p["snap"], "page": p["page"], "type": p["type"], "article_date": p["article_date"],
                        "link": p["link"], "pos": (si, ti), "rows": rows, "above": clean(t["above"]),
                        "path": [clean(h) for h in s["path"]], "effective": eff, "version": v,
                        "header_line": "| " + " | ".join(t["header"]) + " |"}
                v["pages"].add(p["page"])
                v["instances"].append(inst)
                instances.append(inst)
    return instances, list(versions.values())


def histories(instances: list[dict]) -> list[dict]:
    """Per page, link each table to the same table in the next downloads: {"page", "seg", "by_snap": {snap: inst}}."""
    by_page = defaultdict(list)
    for i in instances:
        by_page[i["page"]].append(i)
    out = []
    for page, insts in by_page.items():
        open_ = []
        for snap in sorted({i["snap"] for i in insts}):
            for inst in sorted((i for i in insts if i["snap"] == snap), key=lambda i: i["pos"]):
                v = inst["version"]
                best, best_score = None, None
                for h in open_:
                    last = h["by_snap"][max(h["by_snap"])]
                    lv = last["version"]
                    if snap in h["by_snap"] or lv["seg"] != v["seg"] or lv["ncol"] != v["ncol"]:
                        continue
                    ov = overlap(lv, v)
                    score = (ov, lv["title"] == v["title"], -abs(last["pos"][0] - inst["pos"][0]))
                    if ov >= config.SAME_ROWS_MIN and (best_score is None or score > best_score):
                        best, best_score = h, score
                if best is None:
                    best = {"page": page, "seg": v["seg"], "by_snap": {}}
                    open_.append(best)
                    out.append(best)
                best["by_snap"][snap] = inst
    return out


def groups(hists: list[dict]) -> list[dict]:
    """Histories on different pages showing the identical table in every download they share:
    {"id", "members": [histories], "pages", "timeline": {snap: version}, "seg"}."""
    out = []
    for h in sorted(hists, key=lambda h: (h["page"], min(h["by_snap"]))):
        timeline = {s: i["version"] for s, i in h["by_snap"].items()}
        for g in out:
            shared = set(g["timeline"]) & set(timeline)
            if shared and h["page"] not in g["pages"] and all(g["timeline"][s] is timeline[s] for s in shared):
                g["members"].append(h)
                g["pages"].add(h["page"])
                g["timeline"].update(timeline)
                break
        else:
            out.append({"members": [h], "pages": {h["page"]}, "timeline": dict(timeline), "seg": h["seg"]})
    for k, g in enumerate(out):
        g["id"] = k
    return out
