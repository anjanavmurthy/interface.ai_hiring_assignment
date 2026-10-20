"""Stage 3 - LLM: what each column of each layout means (cached by request text; run live in ingest by tracker.py).

For every layout the LLM says what kind of table it is (offer table, listing, form, calculation example, other)
and, per column, whether it names the product, a condition (term, tier, model year...), a value (rate, APY, fee...),
a measure label (transposed tables) or nothing. Layouts the model leaves out are sent again once.

The conflict stages then use these roles to name each row ("2024-27 Model Year | 60 Months") and to know which
columns hold values to compare.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .. import config
from ..llm import CachedLLM
from .s3_label_columns_prompt import LAYOUT_SCHEMA, SYSTEM
from .table_text import header_key


def render(layout: dict) -> str:
    """How one layout is shown to the LLM: header, titles, example section, page types and example rows."""
    ex = layout["example"]
    return "\n".join([f'<layout id="{layout["id"]}">',
                      f"Header: {layout['header'] or '(no header row)'}",
                      "Titles: " + "; ".join(f'"{t[:70]}"' for t in layout["titles"][:4]),
                      f"Section of the example: \"{ex['section'][:80]}\"",
                      "Page types: " + ", ".join(layout["page_types"]),
                      "Example rows:"] + [r[:300] for r in ex["rows"]] + ["</layout>"])


def labelling_request(layouts: list[dict]) -> str:
    return "\n\n".join(render(lay) for lay in layouts)


def label_columns(layouts: list[dict], llm: CachedLLM, per_call: int, parallel: int = 4) -> list[dict]:
    """The column roles of every layout the LLM answered for, in layout order: the LLM's answer plus the layout's
    header, row and table counts and table ids."""
    def ask(group: list[dict]) -> list[dict]:
        try:
            return llm.ask(SYSTEM, labelling_request(group), LAYOUT_SCHEMA)["layouts"]
        except Exception as e:                    # a failed request only loses its layouts; they are sent again
            print(f"  labelling request failed: {e}")
            return []

    answers: dict[str, dict] = {}
    todo = layouts
    for _round in range(2):                       # second round: layouts left out of an answer
        groups = [todo[i:i + per_call] for i in range(0, len(todo), per_call)]
        with ThreadPoolExecutor(parallel) as pool:
            for got in pool.map(ask, groups):
                answers.update({a["id"]: a for a in got})
        todo = [lay for lay in layouts if lay["id"] not in answers]
        if not todo:
            break
    return [{**answers[lay["id"]], "header": lay["header"], "rows": lay["rows"], "tables": lay["tables"],
             "table_ids": lay["table_ids"]} for lay in layouts if lay["id"] in answers]


def roles_by_header(mapping: list[dict]) -> dict[str, list[str]]:
    """{header key: [role of column 0, role of column 1, ...]} for every labelled layout with a header row whose
    kind is followed (config.TRACKED_TABLE_KINDS); tables of any other kind are not read by the later stages."""
    roles = {}
    for lay in mapping:
        if lay.get("header") and lay.get("kind") in config.TRACKED_TABLE_KINDS:
            header_cells = [c.strip() for c in lay["header"].strip().strip("|").split("|")]
            roles[header_key(header_cells)] = [c["role"] for c in sorted(lay["columns"], key=lambda c: c["index"])]
    return roles

