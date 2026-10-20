"""Facts, step 3 (code + Claude): give every fact the name of the fact it states, so its values can be compared.

Code first puts together pairs written the same way (ignoring case, punctuation and spacing). Then, per fact type,
one request lists the pairs not seen before, each with an example value, plus the names already in use for that
type; Claude names the fact each pair states, reusing a known name when it fits. Later snapshots only send their new
pairs. A pair Claude leaves out, or whose request fails, keeps its own wording as its name. A Grouper made with
`batch_over` (the second pass over page text, kb/facts/wider.py) splits a type with more new pairs than that into
batches, each with the known names closest to it; the FactBook's Grouper sends one request per type, as always.
"""
from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .. import config
from ..llm import CachedLLM
from .extract import Fact
from .group_prompt import SCHEMA, SYSTEM

Key = tuple[str, str, str]          # (type, subject, attribute), normalised


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s/&%$-]", " ", text.lower())).strip()


def key_of(f: Fact) -> Key:
    return f.type, norm(f.subject), norm(f.attribute)


def request(known: list[str], new: list[tuple[str, Fact]]) -> str:
    lines = [f"<known>{name}</known>" for name in sorted(known)]
    lines += [f'<new id="{i}">{f.subject} | {f.attribute} (e.g. "{f.value}")</new>' for i, f in new]
    return "\n".join(lines)


def words(text: str) -> set[str]:
    return set(norm(text).split())


def batches(pairs: dict[Key, Fact], known: list[str], size: int,
            nearby: int) -> list[tuple[dict[Key, Fact], list[str]]]:
    """A large type's new pairs in batches of about `size`, pairs of one subject kept together (sorted by subject, so
    similar subjects tend to share a batch), each batch with the `nearby` known names sharing most words with it."""
    by_subject: dict[str, list[Key]] = defaultdict(list)
    for key in sorted(pairs, key=lambda k: (k[1], k[2])):
        by_subject[key[1]].append(key)
    out: list[dict[Key, Fact]] = [{}]
    for keys in by_subject.values():
        if out[-1] and len(out[-1]) + len(keys) > size:
            out.append({})
        out[-1].update({k: pairs[k] for k in keys})
    known_words = {n: words(n) for n in known}
    result = []
    for batch in out:
        w = set().union(*(words(f"{k[1]} {k[2]}") for k in batch))
        close = sorted(known, key=lambda n: (-len(known_words[n] & w), n))[:nearby]
        result.append((batch, [n for n in close if known_words[n] & w]))
    return result


class Grouper:
    def __init__(self, llm: CachedLLM, batch_over: int | None = None):
        self.llm = llm
        self.batch_over = batch_over                # None: one request per type, however many pairs
        self.name_of: dict[Key, str] = {}           # pair -> the name of the fact it states

    def add(self, facts: list[Fact]) -> None:
        """Name every fact (sets Fact.group), sending Claude only the pairs not named before."""
        new: dict[str, dict[Key, Fact]] = defaultdict(dict)       # type -> pair -> an example fact
        for f in facts:
            if key_of(f) not in self.name_of:
                new[f.type].setdefault(key_of(f), f)
        work: list[tuple[dict[Key, Fact], list[str]]] = []        # (pairs, known names) per request
        for typ, pairs in new.items():
            known = sorted({n for key, n in self.name_of.items() if key[0] == typ})
            if self.batch_over is not None and len(pairs) > self.batch_over:
                work += batches(pairs, known, config.NAMING_BATCH_PAIRS, config.NAMING_NEARBY_KNOWN)
            else:
                work.append((pairs, known))

        def ask(item: tuple[dict[Key, Fact], list[str]]) -> dict[Key, str]:
            pairs, known = item
            ids = {f"n{k + 1}": key for k, key in enumerate(pairs)}
            try:
                answer = self.llm.ask(SYSTEM, request(known, [(i, pairs[key]) for i, key in ids.items()]), SCHEMA)
            except Exception as e:                  # a failed request: its pairs keep their own wording
                print(f"  naming request failed: {e}")
                return {}
            return {ids[a["id"]]: a["name"].strip() for a in answer["names"] if a["id"] in ids and a["name"].strip()}

        with ThreadPoolExecutor(config.LLM_PARALLEL) as pool:
            for (pairs, _), names in zip(work, pool.map(ask, work)):
                for key, f in pairs.items():
                    self.name_of[key] = names.get(key) or f"{f.subject} | {f.attribute}"
        for f in facts:
            f.group = self.name_of[key_of(f)]
