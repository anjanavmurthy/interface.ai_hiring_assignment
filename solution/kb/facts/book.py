"""Facts, step 4: the record of facts, filled one snapshot at a time inside ingest().

For each snapshot: collect the text not read before (step 1), extract its facts (step 2, Claude), name the fact each
one states (step 3, Claude), keep them, and judge the facts found with more than one value (step 5, Claude). Only
facts whose set of values changed since the last judgement are sent again; the verdicts are kept per snapshot, so an
answer "as of" an older snapshot sees what was known then. A fact's pages, snapshots and publish dates come from its
paragraph, which keeps being updated as later snapshots show it again.
"""
from __future__ import annotations

from collections import defaultdict

from ..llm import CachedLLM
from .collect import Collector
from .extract import Fact, extract
from .group import Grouper
from .judge import Verdict, candidates, judge_facts, value_key


class FactBook:
    def __init__(self, extract_llm: CachedLLM, group_llm: CachedLLM, judge_llm: CachedLLM):
        self.extract_llm, self.judge_llm = extract_llm, judge_llm
        self.collector = Collector()
        self.grouper = Grouper(group_llm)
        self.facts: list[Fact] = []
        self.snap_dates: dict[str, str] = {}
        self.verdicts: dict[str, dict[str, Verdict]] = {}     # snapshot '01' -> fact name -> its verdict
        self._judged: dict[str, frozenset[str]] = {}          # fact name -> the values it was last judged with

    def add_snapshot(self, snapshot_id: str, pages: list[tuple[str, str]]) -> list[Fact]:
        """Read one snapshot's pages, given as (url, cleaned text); returns the facts it added."""
        snap = snapshot_id[:2]
        self.snap_dates[snap] = snapshot_id[3:13]
        new, _dropped = extract(self.collector.add_snapshot(snapshot_id, pages), self.extract_llm)
        self.grouper.add(new)
        self.facts += new
        self._judge(snap)
        return new

    def _judge(self, snap: str) -> None:
        current = dict(self.verdicts[max(self.verdicts)]) if self.verdicts else {}
        todo = [(name, values) for name, values in candidates(self.by_fact())
                if frozenset(value_key(v) for v in values) != self._judged.get(name)]
        found, answered = judge_facts(todo, self.judge_llm, self.snap_dates)
        for name, values in todo:
            if name in answered:                  # a failed request leaves the earlier verdict in place
                self._judged[name] = frozenset(value_key(v) for v in values)
                current.pop(name, None)
        current.update({v.name: v for v in found})
        self.verdicts[snap] = current

    def by_fact(self) -> dict[str, list[Fact]]:
        """Every fact's values: name -> the facts that state it."""
        out: dict[str, list[Fact]] = defaultdict(list)
        for f in self.facts:
            out[f.group].append(f)
        return dict(out)
