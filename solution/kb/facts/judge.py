"""Facts, step 5 (Claude): which facts with several values are real contradictions, and the value to tell today.

Runs inside ingest() after each snapshot (book.py), only for facts whose set of values changed.

Code lists the named facts found with more than one value (ignoring how a value is written: emphasis, quotes,
spacing, case). Each distinct value is shown once, with how many pages state it, their publish dates, the downloads
it appeared in and one sentence, so a paragraph copied on eighty pages costs one line. config.FACTS_JUDGE_PER_REQUEST
facts go in a request. Claude's competing values are kept only when they are among the values shown.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from .. import config
from ..cleaning import detailed_page_type, site_path
from ..llm import CachedLLM
from .extract import Fact, plain
from .judge_prompt import SCHEMA, SYSTEM

SENTENCE_CHARS = 300               # how much of the paragraph around the value is shown


@dataclass
class Verdict:
    name: str
    values: dict[str, list[Fact]]      # value as shown -> the facts that state it, competing values only
    correct_value: str
    why: str


def value_key(value: str) -> str:
    return plain(value).lower().strip(" .")


def iso(date: str) -> str:
    """'May 05, 2026' -> '2026-05-05' (unparseable dates are kept as written)."""
    try:
        return datetime.strptime(date, "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return date


def candidates(by_fact: dict[str, list[Fact]]) -> list[tuple[str, dict[str, list[Fact]]]]:
    """(name, {value as shown: facts}) for every named fact with more than one distinct value."""
    out = []
    for name, facts in by_fact.items():
        groups: dict[str, list[Fact]] = defaultdict(list)
        for f in facts:
            groups[value_key(f.value)].append(f)
        if len(groups) > 1:
            out.append((name, {fs[0].value: fs for fs in groups.values()}))
    return out


def sentence(f: Fact) -> str:
    """The part of the fact's paragraph around its value."""
    text, value = plain(f.paragraph.text), plain(f.value)
    at = max(text.find(value), 0)
    start = max(0, at - SENTENCE_CHARS // 2)
    return ("..." if start else "") + text[start:start + SENTENCE_CHARS] + ("..." if start + SENTENCE_CHARS < len(text) else "")


def newest(fs: list[Fact]) -> Fact:
    return max(fs, key=lambda f: max((iso(d) for d in f.paragraph.dates.values()), default=""))


def describe(value: str, fs: list[Fact]) -> str:
    pages = sorted({u for f in fs for u in f.paragraph.seen})
    dates = sorted({iso(d) for f in fs for d in f.paragraph.dates.values()})
    snaps = sorted({s for f in fs for ss in f.paragraph.seen.values() for s in ss})
    refers = sorted({f.refers_to for f in fs if f.refers_to})
    where = (", ".join(f"{site_path(u)}, {detailed_page_type(u)}" for u in pages) if len(pages) <= 2
             else f"e.g. {site_path(pages[0])}, {site_path(pages[-1])}")
    attrs = f' refers_to="{"; ".join(refers)}"' if refers else ""
    published = (f", published {dates[0]}" + (f" to {dates[-1]}" if len(dates) > 1 else "")) if dates else ""
    return (f'<statement value="{value}"{attrs}>{len(pages)} page{"s" * (len(pages) > 1)} ({where}){published}, '
            f'downloads {", ".join(snaps)}. "{sentence(newest(fs))}"</statement>')


def request(batch: list[tuple[str, str, dict[str, list[Fact]]]], snap_dates: dict[str, str]) -> str:
    lines = ["<downloads>" + ", ".join(f"{s} = {d}" for s, d in sorted(snap_dates.items())) + "</downloads>"]
    for fid, name, values in batch:
        lines += [f'<fact id="{fid}" name="{name}">', *(describe(v, fs) for v, fs in values.items()), "</fact>"]
    return "\n".join(lines)


def judge_facts(todo: list[tuple[str, dict[str, list[Fact]]]], llm: CachedLLM,
                snap_dates: dict[str, str]) -> tuple[list[Verdict], set[str]]:
    """(the facts Claude calls real contradictions, with their competing values and the value to tell today; the
    names of all facts Claude answered for). todo: (name, {value: facts}) from candidates()."""
    items = [(f"f{k + 1}", name, values) for k, (name, values) in enumerate(todo)]
    n = config.FACTS_JUDGE_PER_REQUEST
    batches = [items[i:i + n] for i in range(0, len(items), n)]

    def ask(batch) -> list[dict]:
        try:
            return llm.ask(SYSTEM, request(batch, snap_dates), SCHEMA)["facts"]
        except Exception as e:                       # a failed request only loses its own facts
            print(f"  fact judging request failed: {e}")
            return []

    by_id = {fid: (name, values) for fid, name, values in items}
    verdicts, answered = [], set()
    with ThreadPoolExecutor(config.LLM_PARALLEL) as pool:
        for answer in pool.map(ask, batches):
            for a in answer:
                if a["id"] in by_id:
                    answered.add(by_id[a["id"]][0])
                if not a["conflict"] or a["id"] not in by_id:
                    continue
                name, values = by_id[a["id"]]
                shown = {value_key(v): v for v in values}
                competing = list(dict.fromkeys(shown[value_key(v)] for v in a["values"] if value_key(v) in shown))
                if len(competing) < 2:
                    continue
                correct = shown.get(value_key(a["correct_value"]), competing[0])
                verdicts.append(Verdict(name, {v: values[v] for v in competing}, correct, a["why"]))
    return verdicts, answered
