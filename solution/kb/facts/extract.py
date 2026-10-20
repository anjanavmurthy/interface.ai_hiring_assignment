"""Facts, step 2 (Claude): read the collected documents and list the facts they state.

Documents are packed into requests of up to config.FACTS_REQUEST_CHARS, sent config.LLM_PARALLEL at a time. A failed
request only loses its own documents. Code keeps a fact only when every number in its value is written in its
paragraph, so no stored number can be made up; worded values (a role, a status) may be put in Claude's words.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .. import config
from ..llm import CachedLLM
from .collect import Document, Paragraph
from .extract_prompt import SCHEMA, SYSTEM


@dataclass
class Fact:
    paragraph: Paragraph          # where it was read: pages, snapshots and publish dates come from here
    subject: str
    type: str
    attribute: str
    value: str
    refers_to: str
    group: str = ""                # the name of the fact it states (step 3)
    origin: str = "text"           # "text" (a paragraph) or "table" (a table row, kb/bridge)


def render(doc: Document) -> str:
    if doc.url == "footer":
        head = '<page url="(the About-the-credit-union paragraph printed under press releases; each wording below ' \
               'appeared on one or more pages)">'
    else:
        head = f'<page url="{doc.url}"' + (f' published="{doc.article_date}"' if doc.article_date else "") + ">"
    body = [f'<p id="{p.id}">{t}</p>' if p else f"<context>{t}</context>" for t, p in doc.parts]
    return "\n".join([head, *body, "</page>"])


def pack(docs: list[Document], limit: int) -> list[list[Document]]:
    """Documents in request-sized groups, in order; a document larger than the limit goes alone."""
    groups: list[list[Document]] = [[]]
    size = 0
    for d in docs:
        n = len(render(d))
        if groups[-1] and size + n > limit:
            groups.append([])
            size = 0
        groups[-1].append(d)
        size += n
    return [g for g in groups if g]


NUMBER = re.compile(r"\d[\d,.]*")
TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "\u00a0": " "})


def plain(text: str) -> str:
    """Text compared without markdown emphasis, escapes, typographic quotes and dashes, and spacing differences."""
    return re.sub(r"\s+", " ", text.translate(TYPOGRAPHY).replace("**", "").replace("\\", "")).strip()


def grounded(value: str, paragraph: str) -> bool:
    """Every number in the value appears in the paragraph (a worded value without numbers always passes)."""
    text = plain(paragraph)
    return bool(value.strip()) and all(n.rstrip(".,") in text for n in NUMBER.findall(plain(value)))


def extract(docs: list[Document], llm: CachedLLM) -> tuple[list[Fact], int]:
    """(facts, number of facts dropped because a number in their value is not in their paragraph)."""
    by_id = {p.id: p for d in docs for _, p in d.parts if p}

    def ask(group: list[Document]) -> list[dict]:
        try:
            return llm.ask(SYSTEM, "\n\n".join(render(d) for d in group), SCHEMA)["facts"]
        except Exception as e:                       # a failed request only loses its own documents
            print(f"  facts request failed: {e}")
            return []

    facts, dropped = [], 0
    with ThreadPoolExecutor(config.LLM_PARALLEL) as pool:
        for answer in pool.map(ask, pack(docs, config.FACTS_REQUEST_CHARS)):
            for f in answer:
                p = by_id.get(f["p"])
                if p is None or not grounded(f["value"], p.text):
                    dropped += 1
                    continue
                facts.append(Fact(p, f["subject"], f["type"], f["attribute"], f["value"], f["refers_to"]))
    return facts, dropped
