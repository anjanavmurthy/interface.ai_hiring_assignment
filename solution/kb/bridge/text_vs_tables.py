"""Contradictions between page text and tables (config.TEXT_VS_TABLES), run once by conflicts().

The table stages compare tables with tables and the fact stages compare text with text; neither sees a sentence that
disagrees with a table. This step reads both without changing either. Code organises, Claude judges:

1. every table the table stages follow (stage s4's versions: one table as shown in one download, with every page
   that shows it) is a candidate;
2. for each, code shortlists the text facts of the same download whose subject is close in meaning to the table's
   title, alone or with one of its products (config.TEXT_VS_TABLES_SIMILAR, at most config.TEXT_VS_TABLES_PER_TABLE),
   and whose value has a figure the table does not show anywhere, of a kind its value cells hold (a rate, an amount):
   a fee cannot contradict a rate column, and a sentence repeating the table's own figures is never sent;
3. Claude gets each table with its shortlist (text_vs_tables_prompt.py) and says, per sentence, whether it is about a
   row and column of the table and whether it contradicts it; a table and sentence seen in several downloads are
   asked about once;
4. a contradiction is kept when no conflict already found has two of the same values (the table and fact stages
   keep their own conflicts as they are).
"""
from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .. import config
from ..cleaning.page_info import SITE
from ..conflicts.s4_track_tables import read_versions
from ..conflicts.table_text import clean, header_key, norm_value
from ..facts.collect import Paragraph
from ..facts.extract import Fact
from ..facts.judge import Verdict, iso, sentence, value_key
from ..llm import CachedLLM
from .text_vs_tables_prompt import SCHEMA, SYSTEM

FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def units(text: str) -> set[str]:
    """The kinds of figure in a text: '%' (a rate), '$' (an amount), or '#' (another number)."""
    out = {u for u in ("%", "$") if u in (text or "")}
    return out or ({"#"} if FIGURE.search(text or "") else set())


def figures(text: str) -> set[str]:
    """The numbers in a text, written one way: '4.170%' and '4.17' are both '4.17', '$2,345' is '2345'."""
    return {f.replace(",", "").rstrip(".").rstrip("0").rstrip(".") if "." in f else f.replace(",", "")
            for f in FIGURE.findall(text or "")}


class Table:
    """One table as shown in one download (a stage-s4 version)."""

    def __init__(self, version: dict, products: list[str], effective: str | None):
        self.snap, self.title, self.header = version["snap"], version["title"], version["header"]
        self.rows = [[clean(x) for x in r] for r in version["instances"][0]["rows"]]
        self.pages = sorted(version["pages"])
        self.effective = effective
        self.products = products
        self.figures = set().union(*(figures(" ".join(r)) for r in self.rows)) if self.rows else set()
        value_cols = version["value_cols"]
        self.units = set().union(*(units(r[j]) for r in self.rows for j in value_cols if j < len(r))) or {"#"}
        self.key = (self.title, tuple(self.header), tuple(tuple(r) for r in self.rows))

    def names(self) -> list[str]:
        """What a sentence about this table would name: the title, and the title with each product."""
        return [self.title] + [f"{self.title} {p}" for p in self.products]

    def render(self, tid: str, downloads: str) -> str:
        head = (f'<table id="{tid}" title="{self.title}" download="{downloads}" pages="{", ".join(self.pages[:4])}"'
                + (f' effective="{self.effective}"' if self.effective else "") + ">")
        lines = [head, "| " + " | ".join(self.header) + " |"] + ["| " + " | ".join(r) + " |" for r in self.rows]
        return "\n".join(lines + ["</table>"])


def tables_of(tracker) -> list[Table]:
    """Every followed table as shown in each download, with its product names (from the s3 column roles)."""
    _, versions = read_versions(tracker.pages, tracker.roles_of())
    out = []
    for v in versions:
        roles = tracker.roles_of().get(header_key(v["instances"][0]["header_line"].strip().strip("|").split("|")), [])
        product_cols = [j for j, r in enumerate(roles) if r == "product"]
        products = sorted({clean(r[j]) for r in v["instances"][0]["rows"] for j in product_cols if j < len(r)} - {""})
        effective = next((i["effective"] for i in v["instances"] if i["effective"]), None)
        out.append(Table(v, products, effective))
    return out


def statement(f: Fact, sid: str, tid: str) -> str:
    pages = sorted(f.paragraph.seen)
    dates = sorted({iso(d) for d in f.paragraph.dates.values()})
    page = pages[0].replace(SITE, "") if pages else ""
    published = f' published="{dates[-1]}"' if dates else ""
    return f'<statement id="{sid}" table="{tid}" value="{f.value}" page="{page}"{published}>"{sentence(f)}"</statement>'


def text_vs_tables(text_facts: list[Fact], tracker, existing: list, embedder, judge_llm: CachedLLM,
                   snap_dates: dict[str, str]) -> list[Verdict]:
    """The contradictions between a sentence and a table row, not already among `existing` conflicts."""
    tables = tables_of(tracker)
    by_snap: dict[str, list[Fact]] = defaultdict(list)
    for f in text_facts:
        if figures(f.value):
            for snap in {s for ss in f.paragraph.seen.values() for s in ss}:
                by_snap[snap].append(f)
    subjects = sorted({f.subject for f in text_facts if figures(f.value)})
    names = sorted({n for t in tables for n in t.names()})
    if not subjects or not names or embedder.embed(subjects[:1]) is None:
        return []
    sv = dict(zip(subjects, embedder.embed(subjects)))
    nv = dict(zip(names, embedder.embed(names)))

    pairs: dict[tuple, dict] = {}                               # (table key, fact id) -> what to ask, downloads
    for t in tables:
        tv = [nv[n] for n in t.names()]
        close = [(max(float(sv[f.subject] @ v) for v in tv), f) for f in by_snap.get(t.snap, [])
                 if units(f.value) & t.units and not figures(f.value) <= t.figures]
        close = sorted((x for x in close if x[0] >= config.TEXT_VS_TABLES_SIMILAR), key=lambda x: -x[0])
        for _, f in close[:config.TEXT_VS_TABLES_PER_TABLE]:
            p = pairs.setdefault((t.key, id(f)), {"table": t, "fact": f, "snaps": set()})
            p["snaps"].add(t.snap)
    by_table: dict[tuple, list[dict]] = defaultdict(list)
    for p in pairs.values():
        by_table[p["table"].key].append(p)

    items = list(by_table.values())
    n = config.TEXT_VS_TABLES_TABLES_PER_REQUEST
    batches = [items[i:i + n] for i in range(0, len(items), n)]

    def ask(batch) -> list[tuple[dict, dict]]:
        blocks, ids = [], {}
        for k, group in enumerate(batch):
            tid = f"t{k + 1}"
            snaps = sorted({s for p in group for s in p["snaps"]})
            blocks.append(group[0]["table"].render(tid, ", ".join(snaps)))
            for j, p in enumerate(group):
                sid = f"s{k + 1}_{j + 1}"
                ids[sid] = p
                blocks.append(statement(p["fact"], sid, tid))
        downloads = "<downloads>" + ", ".join(f"{s} = {d}" for s, d in sorted(snap_dates.items())) + "</downloads>"
        try:
            answer = judge_llm.ask(SYSTEM, "\n".join([downloads, *blocks]), SCHEMA)["statements"]
        except Exception as e:                       # a failed request only loses its own tables
            print(f"  text vs tables request failed: {e}")
            return []
        return [(ids[a["id"]], a) for a in answer if a["id"] in ids]

    found: list[Verdict] = []
    with ThreadPoolExecutor(config.LLM_PARALLEL) as pool:
        for answers in pool.map(ask, batches):
            for p, a in answers:
                if a["about_table"] and a["contradicts"]:
                    v = verdict(p, a)
                    if v and not overlaps_existing(v, existing + found):
                        found.append(v)
    return found


def verdict(p: dict, a: dict) -> Verdict | None:
    """The conflict between the sentence and the cell the judge named, as a Verdict like the fact judge's."""
    t, f = p["table"], p["fact"]
    col = next((j for j, h in enumerate(t.header) if h.strip().lower() == a["column"].strip().lower()), None)
    row = next((r for r in t.rows if a["row"].strip().lower() in " | ".join(r).lower()), None) if a["row"] else None
    if col is None or row is None or col >= len(row) or not row[col]:
        return None
    cell_value = row[col]
    if value_key(cell_value) == value_key(f.value):
        return None
    record = Paragraph("", f"{t.title}: | {' | '.join(t.header)} | | {' | '.join(row)} |")
    for page in t.pages:
        record.seen[SITE + page] = set(p["snaps"])
    cell = Fact(record, a["row"], "product", a["column"], cell_value, "", origin="table")
    correct = f.value if value_key(a["correct_value"]) == value_key(f.value) else cell_value
    return Verdict(f"{t.title} {a['row']} | {a['column']}", {cell_value: [cell], f.value: [f]}, correct, a["why"])


def overlaps_existing(v: Verdict, existing: list) -> bool:
    """A conflict already found has two of the same values."""
    mine = {norm_value(x) for x in v.values}
    return any(len(mine & {norm_value(x) for x in c.values}) >= 2 for c in existing)
