"""
Knowledge system for the Dupaco website snapshots - the entry point the scorer loads.

    ingest(snapshot)        clean every page, chunk it, build a keyword + embedding index for that snapshot;
                            read its tables and have Claude label the columns of table layouts not seen before;
                            have Claude list the facts in its text not read before, name them, and judge the facts
                            found with more than one value (kb/facts)
    answer(question, as_of) pick the snapshot on/before as_of, retrieve the top chunks, one Claude call
    conflicts()             contradictions with the value believed right: the facts judged in ingest (kb/facts step 5)
                            and the look-alike tables, which Claude judges (s4-s7) once, on the first call

The work is done by the kb/ package (cleaning -> retrieval -> qa, plus conflicts); this file only wires the
stages together. Needs ANTHROPIC_API_KEY for answers and table labelling; without it every answer is an honest
"I don't know" and no table is labelled or fact read.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# the scorer's data classes (Answer, Source, Conflict, Snapshot) live in harness/contract.py
sys.path.insert(0, str(next(d / "harness" for d in HERE.parents if (d / "harness" / "contract.py").exists())))

from contract import Answer, Snapshot  # noqa: E402

from kb import config  # noqa: E402
from kb.budget import Deadline  # noqa: E402
from kb.cleaning import clean_page, is_listing_page  # noqa: E402
from kb.conflicts.pipeline import find_table_conflicts  # noqa: E402
from kb.conflicts.report import fact_conflict, table_conflict  # noqa: E402
from kb.conflicts.tracker import TableTracker  # noqa: E402
from kb.env import load_dotenv  # noqa: E402
from kb.bridge.text_vs_tables import text_vs_tables  # noqa: E402
from kb.facts.book import FactBook  # noqa: E402
from kb.facts.wider import WiderFacts  # noqa: E402
from kb.changes import ChangeLog  # noqa: E402
from kb.history import History  # noqa: E402
from kb.llm import CachedLLM  # noqa: E402
from kb.qa import Answerer, make_client  # noqa: E402
from kb.retrieval import Embedder, SnapshotIndex, chunk_page  # noqa: E402

load_dotenv(HERE.parent / ".env", HERE / ".env")

NO_DATA = "I don't have any information from the website for that date."


class KnowledgeSystem:
    def __init__(self):
        self.snapshots: list[tuple[str, str, SnapshotIndex]] = []   # (taken_on, snapshot_id, index), oldest first
        self.embedder = Embedder()
        self._answers: dict[tuple[str, str], Answer] = {}            # (normalised question, snapshot) -> Answer
        self.deadline = Deadline(config.INGEST_BUDGET_S, config.INGEST_HARD_STOP_S)  # past it, no new Claude requests
        self.tables = TableTracker(CachedLLM(config.COLUMN_LABELS_CACHE, config.CONFLICTS_MODEL,
                                             config.CONFLICTS_EFFORT, self.deadline))
        self.facts = FactBook(CachedLLM(config.FACTS_CACHE, config.FACTS_MODEL, config.FACTS_EFFORT, self.deadline),
                              CachedLLM(config.FACTS_GROUP_CACHE, config.FACTS_MODEL, config.FACTS_GROUP_EFFORT,
                                        self.deadline),
                              CachedLLM(config.FACTS_JUDGE_CACHE, config.FACTS_MODEL, config.FACTS_JUDGE_EFFORT,
                                        self.deadline))
        # a second pass over page text whose facts feed conflicts() only; the FactBook above is unchanged
        self.wider = WiderFacts(CachedLLM(config.FACTS_MORE_CACHE, config.FACTS_MORE_MODEL, config.FACTS_MORE_EFFORT,
                                          self.deadline),
                                CachedLLM(config.FACTS_MORE_NAMES_CACHE, config.FACTS_MODEL, config.FACTS_GROUP_EFFORT,
                                          self.deadline),
                                CachedLLM(config.FACTS_MORE_JUDGE_CACHE, config.FACTS_MODEL, config.FACTS_JUDGE_EFFORT,
                                          self.deadline)) if config.FACTS_READ_MORE else None
        self._conflicts: list | None = None
        self.history = History(self.embedder)                         # dated fact values, searched by the question
        self.changes = ChangeLog()                                    # page sections that changed between downloads
        self.answerer = Answerer(make_client(), self.history if config.ANSWER_HISTORY else None,
                                 self.changes if config.ANSWER_HISTORY else None)

    # ------------------------------------------------------------------ ingest
    def ingest(self, snapshot: Snapshot) -> None:
        self.deadline.start()
        chunks, cleaned_pages = [], []
        for page in snapshot.pages:
            cleaned = clean_page(page.markdown)
            cleaned_pages.append((page.url, cleaned.text))
            if not is_listing_page(page.url):
                chunks += chunk_page(page.url, page.title, cleaned.text, page.fetched_at, cleaned.links)
        self.snapshots.append((snapshot.taken_on, snapshot.snapshot_id, SnapshotIndex(chunks, self.embedder)))
        self.snapshots.sort()
        self.tables.add_snapshot(snapshot.snapshot_id, cleaned_pages)
        new_facts = self.facts.add_snapshot(snapshot.snapshot_id, cleaned_pages)
        if self.wider:
            self.wider.add_snapshot(snapshot.snapshot_id, cleaned_pages, self.facts, new_facts, self.tables)
        self.history.rebuild(self.facts, self.wider if config.HISTORY_NEW_WARNINGS else None)
        self.changes.add_snapshot(snapshot.snapshot_id, cleaned_pages)

    # ------------------------------------------------------------------ answer
    def snapshot_for(self, as_of=None):
        """The newest snapshot taken on or before `as_of` (the latest one when no date is given)."""
        if as_of is None:
            return self.snapshots[-1] if self.snapshots else None
        on_or_before = [s for s in self.snapshots if s[0] <= str(as_of)[:10]]
        return on_or_before[-1] if on_or_before else None

    def answer(self, question: str, as_of=None) -> Answer:
        snap = self.snapshot_for(as_of)
        if snap is None:
            return Answer(text=NO_DATA, confident=False)
        taken_on, snapshot_id, index = snap
        # the same question (ignoring case and spacing) on the same snapshot always gets the same answer
        key = (" ".join(question.lower().split()), snapshot_id)
        if key not in self._answers:
            # the download dates up to the one answered from: '01 = 2026-05-12, 02 = 2026-05-19, ...'
            downloads = ", ".join(f"{sid[:2]} = {sid[3:13]}" for _, sid, _ in self.snapshots if sid <= snapshot_id)
            self._answers[key] = self.answerer.answer(question, taken_on, snapshot_id, index, as_of, downloads)
        return self._answers[key]

    # ------------------------------------------------------------------ conflicts
    def conflicts(self):
        """Table conflicts and fact conflicts, the value to tell a member today first. Judged once, then kept."""
        if self._conflicts is None:
            ids = {sid[:2]: sid for _, sid, _ in self.snapshots}
            judge = CachedLLM(config.CONFLICT_JUDGE_CACHE, config.CONFLICTS_MODEL, config.CONFLICTS_EFFORT)
            tables = find_table_conflicts(self.tables.pages, self.tables.roles_of(), judge, self.tables.snap_dates)
            verdicts = (self.wider or self.facts).verdicts         # with more page text: its verdicts, for conflicts
            facts = verdicts[max(verdicts)].values() if verdicts else []
            self._conflicts = ([table_conflict(r, ids) for r in tables.facts]
                               + [fact_conflict(v, ids) for v in facts])
            if config.TEXT_VS_TABLES:
                text_facts = self.facts.facts + (self.wider.facts if self.wider else [])
                found = text_vs_tables(
                    text_facts, self.tables, self._conflicts, self.embedder,
                    CachedLLM(config.TEXT_VS_TABLES_JUDGE_CACHE, config.FACTS_MODEL, config.FACTS_JUDGE_EFFORT),
                    self.facts.snap_dates)
                self._conflicts += [fact_conflict(v, ids) for v in found]
        return self._conflicts


def build() -> KnowledgeSystem:
    return KnowledgeSystem()
