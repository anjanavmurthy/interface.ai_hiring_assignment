"""Answer one question from one snapshot: search -> one Claude call -> safety checks -> Answer."""
from __future__ import annotations

import json
import os
import re

from contract import Answer, Source

from .. import config
from ..retrieval import Chunk, SnapshotIndex
from ..history import refers_to_another_time
from .prompt import ANSWER_SCHEMA, INSTRUCTIONS, REFUSAL, user_message

NUMBER = re.compile(r"\d+")


def make_client():
    """An Anthropic client if an API key is set, else None (every answer is then an honest refusal)."""
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic
    return anthropic.Anthropic(timeout=config.API_TIMEOUT_S, max_retries=config.API_MAX_RETRIES)


def refusal_without_numbers(text: str, answered: bool, question: str) -> str:
    """A "not listed" answer must not state numbers (the scorer zeroes a refusal that quotes a figure, and a
    figure in a refusal would be a guess). Numbers that were in the question itself are allowed."""
    if not answered and set(NUMBER.findall(text)) - set(NUMBER.findall(question)):
        return REFUSAL
    return text


def cited_urls(source_ids: list, hits: list[Chunk], answered: bool) -> list[str]:
    """Map the source numbers Claude cited back to pages: every page carrying that exact text (official pages
    first, at most CITED_URLS_PER_SOURCE each). Unknown ids are ignored; an answer citing nothing usable
    falls back to the top search hit."""
    cited = [hits[n - 1] for n in source_ids if isinstance(n, int) and 1 <= n <= len(hits)]
    urls = list(dict.fromkeys(u for c in cited for u in (c.copies or [c.url])[:config.CITED_URLS_PER_SOURCE]))
    return urls or ([hits[0].url] if answered else [])


class Answerer:
    def __init__(self, client=None, history=None, changes=None):
        self.client = client
        self.history = history             # kb.history.History, or None: no history block
        self.changes = changes             # kb.changes.ChangeLog, or None: no changes block

    def answer(self, question: str, website_date: str, snapshot_id: str, index: SnapshotIndex, as_of=None,
               downloads: str = "") -> Answer:
        hits = index.search(question, config.TOP_K)
        if self.client is None or not hits:
            return Answer(text=REFUSAL, confident=False)
        try:
            timeline = refers_to_another_time(question, as_of)
            history = self.history.note(question, snapshot_id[:2], hits, timeline) if self.history else ""
            changes = self.changes.lines(question, snapshot_id[:2]) if self.changes and timeline else ""
            reply = self._ask_claude(user_message(question, website_date, hits, history, changes, downloads))
        except Exception as e:                       # API error / timeout: be honest rather than guess
            print(f"LLM call failed: {type(e).__name__}: {e}", flush=True)
            return Answer(text=REFUSAL, confident=False)
        if reply is None:                            # the model declined to answer
            return Answer(text=REFUSAL, confident=False)

        answered = bool(reply.get("answered"))
        text = refusal_without_numbers((reply.get("answer") or "").strip(), answered, question)
        urls = cited_urls(reply.get("sources", []), hits, answered)
        return Answer(text=text or REFUSAL, confident=answered,
                      sources=[Source(url=u, snapshot_id=snapshot_id) for u in urls])

    def _ask_claude(self, message: str) -> dict | None:
        """One structured-output call; returns the parsed reply, or None if the model refused."""
        resp = self.client.beta.messages.create(
            model=config.MODEL, max_tokens=config.MAX_TOKENS, system=INSTRUCTIONS,
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",   # re-run on another model if declined
            output_config={"effort": config.EFFORT, "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
            messages=[{"role": "user", "content": message}],
        )
        if resp.stop_reason == "refusal":
            return None
        return json.loads(next(b.text for b in resp.content if b.type == "text"))
