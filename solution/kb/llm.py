"""A cached LLM caller for the offline-style stages (column labelling, conflict judging).

Each call sends a system prompt + one message and gets JSON back in a fixed shape (structured output). Answers are
stored in a JSON file keyed by model + effort + prompt + message, so an unchanged request is free and gives the
same answer every time; changing any of the four asks again. (Q&A uses its own fast, uncached call: kb/qa.)
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

# $ per million tokens (input, output), for the cost line printed after a run
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}


class CachedLLM:
    def __init__(self, cache_file: Path, model: str, effort: str, deadline=None):
        self.cache_file, self.model, self.effort = cache_file, model, effort
        self.deadline = deadline                               # kb.budget.Deadline: no new requests after it
        self.cache: dict[str, dict] = json.loads(cache_file.read_text()) if cache_file.exists() else {}
        self.used = {"calls": 0, "in": 0, "cache_write": 0, "cache_read": 0, "out": 0}   # new (paid) calls by this object
        self._lock = threading.Lock()                          # stages send several requests in parallel
        self._client = None

    def key(self, system: str, user: str) -> str:
        return hashlib.sha1(f"{self.model}\n{self.effort}\n{system}\n{user}".encode()).hexdigest()

    def is_cached(self, system: str, user: str) -> bool:
        return self.key(system, user) in self.cache

    def ask(self, system: str, user: str, schema: dict) -> dict:
        """The answer as a dict: from the cache if this exact request was sent before, else from the API."""
        key = self.key(system, user)
        if key in self.cache:
            return self.cache[key]
        if self.deadline is not None and self.deadline.passed():
            raise TimeoutError("ingest time budget used up; request skipped")
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(timeout=900, max_retries=2)   # long answers: allow up to 15 min
        # each attempt (the SDK makes up to 3) may stay silent at most a third of the time left before the hard stop,
        # so a request that hangs near the end cannot carry ingest past the scorer's limit
        left = self.deadline.seconds_left() if self.deadline is not None else None
        client = self._client if left is None else self._client.with_options(timeout=max(min(900, left / 3), 10))
        # the instructions are the same for every request of a stage: cached by the API, later requests pay ~10% for them
        with client.messages.stream(model=self.model, max_tokens=64000,
                                    system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                                    messages=[{"role": "user", "content": user}],
                                    output_config={"effort": self.effort,
                                                   "format": {"type": "json_schema", "schema": schema}}) as s:
            msg = s.get_final_message()
        if msg.stop_reason != "end_turn":
            raise RuntimeError(f"stop_reason {msg.stop_reason}")
        data = json.loads(next(b.text for b in msg.content if b.type == "text"))
        with self._lock:
            self.cache[key] = data
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(self.cache))
            self.used["calls"] += 1
            self.used["in"] += msg.usage.input_tokens
            self.used["cache_write"] += msg.usage.cache_creation_input_tokens or 0
            self.used["cache_read"] += msg.usage.cache_read_input_tokens or 0
            self.used["out"] += msg.usage.output_tokens
        return data

    def cost(self) -> str:
        """'N new calls, X in / Y out tokens, ~$Z' for the calls this object actually paid for."""
        pin, pout = PRICES.get(self.model, (0, 0))
        u = self.used
        paid_in = u["in"] + 1.25 * u["cache_write"] + 0.1 * u["cache_read"]      # cache writes +25%, reads -90%
        return (f"{u['calls']} new calls, {u['in'] + u['cache_write'] + u['cache_read']:,} in "
                f"({u['cache_read']:,} from the prompt cache) / {u['out']:,} out tokens, "
                f"~${paid_in / 1e6 * pin + u['out'] / 1e6 * pout:.2f}")
