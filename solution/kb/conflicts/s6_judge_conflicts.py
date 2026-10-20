"""Stage 6 - LLM: one comparison request per comparison set; the judge decides what is a conflict (cached).

Each request shows every table of the set with all its rows and values per download, exactly as written (rows are
only matched by exact name, never merged by code). The judge decides which tables are the same thing (different
options of a product are different things), which cells state the same fact, which differences are conflicts, and
the value a member should be told now.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..llm import CachedLLM
from .s5_pick_comparisons import rows_of
from .s6_judge_prompt import SCHEMA, SYSTEM
from .table_text import clean


def compress(timeline: dict[str, str]) -> str:
    """{'01': '6.00%', '02': '6.00%', '03': '6.10%'} -> '01-02 6.00%, 03 6.10%'."""
    parts, run = [], []
    for s in sorted(timeline):
        if run and timeline[s] == timeline[run[-1]] and int(s) == int(run[-1]) + 1:
            run.append(s)
        else:
            if run:
                parts.append((run, timeline[run[0]]))
            run = [s]
    if run:
        parts.append((run, timeline[run[0]]))
    return ", ".join((f"{r[0]}-{r[-1]}" if len(r) > 1 else r[0]) + f" {clean(v)}" for r, v in parts)


def header_of(g: dict) -> list[str]:
    """The group's header row in its newest download."""
    return g["timeline"][max(g["timeline"])]["header"]


def describe(table_id: str, g: dict) -> str:
    """One table as the judge sees it: pages, customer type, titles, headings, columns, effective dates, rows."""
    s = max(g["timeline"])
    pages = sorted({(i["page"], i["type"]) for m in g["members"] for i in m["by_snap"].values()})
    newest = next(m["by_snap"][s] for m in g["members"] if s in m["by_snap"])
    titles = list(dict.fromkeys(g["timeline"][x]["title"] for x in sorted(g["timeline"])))
    eff = compress({x: i["effective"] for x in g["timeline"] for i in [g["members"][0]["by_snap"].get(x)]
                    if i and i["effective"]})
    head = header_of(g)
    lines = [f'<table id="{table_id}">',
             f'pages: {", ".join(f"{p} ({t})" for p, t in pages)}',
             f'customer type: {g["seg"]}; downloads present: {", ".join(sorted(g["timeline"]))}',
             f'line above the table (newest): {newest["above"] or "(none)"}',
             f'titles over time: {" / ".join(titles)}',
             f'headings (newest): {" > ".join(newest["path"]) or "(none)"}',
             f'columns: {" | ".join(head)}; effective dates: {eff or "(none)"}',
             "rows:"]
    for name, cols in rows_of(g).items():
        vals = "; ".join(f"{head[j] if j < len(head) else f'column {j + 1}'}: {compress(tl)}" for j, tl in cols.items())
        lines.append(f'"{name}" | {vals}')
    return "\n".join(lines + ["</table>"])


def comparison_request(comparison_set: list[dict], snap_dates: dict[str, str]) -> str:
    """The message for one set: the download dates, then tables T1, T2, ..."""
    downloads = ", ".join(f"{s} = {snap_dates[s]}" for s in sorted(snap_dates))
    return "\n".join([f"<downloads>{downloads}</downloads>"]
                     + [describe(f"T{k}", g) for k, g in enumerate(comparison_set, 1)])


def judge_all(requests: list[str], llm: CachedLLM, parallel: int) -> list[dict | None]:
    """The judge's answer to every request, in order; a failed request gives None and the others still run."""
    def ask(q: str) -> dict | None:
        try:
            return llm.ask(SYSTEM, q, SCHEMA)
        except Exception as e:
            print(f"  request failed: {e}")
            return None

    with ThreadPoolExecutor(parallel) as pool:
        return list(pool.map(ask, requests))
