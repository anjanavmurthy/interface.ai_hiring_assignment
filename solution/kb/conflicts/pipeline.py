"""The comparison stages in running order: find_table_conflicts() runs s4 -> s5 -> s6 -> s7.

s1-s3 run inside ingest(), one snapshot at a time (tracker.py); this takes what they produced (the pages read by s1
and the column roles from s3) and an LLM with a cache, writes no files and prints nothing; the caller decides what
to keep. With every request cached, a run costs nothing and repeats exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import config
from ..llm import CachedLLM
from .s4_track_tables import groups, histories, read_versions
from .s5_pick_comparisons import comparison_sets
from .s6_judge_conflicts import comparison_request, judge_all
from .s6_judge_prompt import SYSTEM as JUDGE_SYSTEM
from .s7_write_conflicts import write_conflicts


@dataclass
class TableConflictRun:
    """Everything one run of s4-s7 produced, for the caller to keep or show."""
    instances: list[dict]                 # every table on every page in every download
    versions: list[dict]                  # identical tables in one download, merged
    groups: list[dict]                    # pages that always show the same table
    sets: list[list[dict]]                # comparison sets, one comparison request each
    requests: list[str]
    answers: list[dict | None] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)          # one per conflict
    bad_refs: list[dict] = field(default_factory=list)       # cells the judge named that do not exist
    cases: list[dict] = field(default_factory=list)          # per set: tables, answer, differences not called


def find_table_conflicts(pages: list[dict], roles_of: dict[str, list[str]], llm: CachedLLM,
                         snap_dates: dict[str, str], ask: bool = True) -> TableConflictRun:
    """Conflicts in tables across pages and downloads. pages: s1 outline_page() for every page of every download;
    roles_of: s3 roles by header row; snap_dates: {'01': '2026-05-12', ...}. With ask=False the requests are built
    but not asked (to estimate the cost first)."""
    instances, versions = read_versions(pages, roles_of)
    gs = groups(histories(instances))
    sets = comparison_sets(gs)
    run = TableConflictRun(instances, versions, gs, sets, [comparison_request(s, snap_dates) for s in sets])
    if ask:
        run.answers = judge_all(run.requests, llm, config.LLM_PARALLEL)
        run.facts, run.bad_refs, run.cases = write_conflicts(sets, run.answers, sorted(snap_dates))
    return run


def uncached_requests(run: TableConflictRun, llm: CachedLLM) -> list[str]:
    """The comparison requests that would cost money (not in the cache)."""
    return [q for q in run.requests if not llm.is_cached(JUDGE_SYSTEM, q)]
