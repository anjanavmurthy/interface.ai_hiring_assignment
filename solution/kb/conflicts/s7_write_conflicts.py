"""Stage 7 - turn the judge's answers into conflict records (code only).

One record per conflict the judge lists, with every cell that states the fact and every value it had per page and
download, labelled "same day" (pages disagreed within one download) and/or "over time" (a value changed between
downloads). Also kept, for review: differences code can see in a judged group that the judge did not call a
conflict, and cells the judge named that do not exist.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .s5_pick_comparisons import rows_of
from .s6_judge_conflicts import header_of
from .table_text import norm_value


def resolve(comparison_set: list[dict], ref: dict):
    """A cell named by the judge ({table: 'T2', row, column}) -> (group, row name, column index), or None."""
    m = re.fullmatch(r"T(\d+)", ref["table"].strip())
    if not m or not 1 <= int(m[1]) <= len(comparison_set):
        return None
    g = comparison_set[int(m[1]) - 1]
    rows = rows_of(g)
    row = ref["row"].strip().strip('"')
    if row not in rows:
        return None
    head = [h.lower() for h in header_of(g)]
    col = ref["column"].strip().lower()
    j = next((j for j in rows[row] if j < len(head) and head[j] == col), None)
    if j is None:
        j = next((j for j in rows[row] if j < len(head) and (col in head[j] or head[j] in col)), None)
    return (g, row, j) if j is not None else None


def observations(g: dict, row: str, j: int) -> list[dict]:
    """Every place a cell was seen: one entry per download and page, with its value and context."""
    out = []
    for s, v in sorted(g["timeline"].items()):
        if row not in v["names"]:
            continue
        k = v["names"].index(row)
        for m in g["members"]:
            i = m["by_snap"].get(s)
            if i and k < len(i["rows"]) and j < len(i["rows"][k]):
                r = i["rows"][k]
                out.append({"snap": s, "page": i["page"], "type": i["type"], "value": r[j], "effective": i["effective"],
                            "article_date": i["article_date"], "context": v["title"], "header": i["header_line"],
                            "row": "| " + " | ".join(r) + " |", "link": i["link"]})
    return out


def kinds_of(cells: list[dict]) -> tuple[list[str], bool]:
    """(downloads in which the cells disagree, whether any cell changed between downloads)."""
    by_snap = defaultdict(set)
    over_time = False
    for c in cells:
        timeline = {o["snap"]: norm_value(o["value"]) for o in c["obs"]}
        over_time |= len(set(timeline.values())) > 1
        for s, x in timeline.items():
            by_snap[s].add(x)
    same = sorted(s for s, xs in by_snap.items() if len(xs) > 1 and len(cells) > 1)
    return same, over_time


def unclaimed_differences(comparison_set: list[dict], answer: dict | None, claimed: set,
                          snaps: list[str]) -> list[list[dict]]:
    """Differences code can see (same row and column name within a judged group, or a change over time) that the
    judge did not list as a conflict."""
    ids = {f"T{k}": g for k, g in enumerate(comparison_set, 1)}
    out = []
    for grp in (answer or {}).get("groups", []):
        gs = [ids[t] for t in grp["tables"] if t in ids]
        cells = defaultdict(list)
        for g in gs:
            head = header_of(g)
            for row, cols in rows_of(g).items():
                for j, tl in cols.items():
                    cells[(row, head[j].lower() if j < len(head) else str(j))].append((g, row, j, tl))
        for (_row, _col), cs in cells.items():
            if any((g["id"], r, j) in claimed for g, r, j, _ in cs):
                continue
            vals = [{s: norm_value(x) for s, x in tl.items()} for *_, tl in cs]
            same_day = any(len({v[s] for v in vals if s in v}) > 1 for s in snaps)
            over = any(len(set(v.values())) > 1 for v in vals)
            if same_day or over:
                out.append([{"group": g["id"], "row": r, "j": j, "obs": observations(g, r, j)} for g, r, j, _ in cs])
    return out


def write_conflicts(sets: list[list[dict]], answers: list[dict | None], snaps: list[str]):
    """(facts, bad_refs, cases): one fact per judged conflict; cells the judge named that don't exist; and per
    comparison set its tables, the answer and the differences not called conflicts."""
    facts, bad_refs, cases = [], [], []
    for n, (c, ans) in enumerate(zip(sets, answers)):
        claimed = set()
        for k, conf in enumerate((ans or {}).get("conflicts", [])):
            cells = []
            for ref in conf["cells"]:
                r = resolve(c, ref)
                if r is None:
                    bad_refs.append({"cluster": n, **ref})
                    continue
                g, row, j = r
                claimed.add((g["id"], row, j))
                cells.append({"group": g["id"], "row": row, "j": j, "obs": observations(g, row, j)})
            if not cells:
                continue
            same, over = kinds_of(cells)
            g0 = next(g for g in c if g["id"] == cells[0]["group"])
            col = header_of(g0)[cells[0]["j"]] if cells[0]["j"] < len(header_of(g0)) else ""
            title = g0["timeline"][max(g0["timeline"])]["title"]
            facts.append({"key": f"[{g0['seg']}] {title} :: {cells[0]['row']} :: {col} #c{n}.{k}", "seg": g0["seg"],
                          "title": title, "label": cells[0]["row"], "column": col, "cluster": n, "cells": cells,
                          "seen": [o for x in cells for o in x["obs"]], "same_snapshot": same, "over_time": over,
                          "kinds": (["same day"] if same else []) + (["over time"] if over else []),
                          "verdict": "conflict", "correct_value": conf["correct_value"], "why": conf["why"]})
        cases.append({"cluster": c, "answer": ans, "unclaimed": unclaimed_differences(c, ans, claimed, snaps)})
    return facts, bad_refs, cases
