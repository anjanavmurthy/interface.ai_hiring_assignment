"""Tests for the ingest time budget: past the deadline no new request is sent, answers already saved still are used."""
import time

import pytest

from kb.budget import Deadline
from kb.llm import CachedLLM


def test_deadline_starts_with_the_first_ingest_and_then_passes():
    d = Deadline(0.01)
    assert not d.passed()                     # not started yet
    d.start()
    time.sleep(0.02)
    assert d.passed()


def test_no_new_request_after_the_deadline_but_saved_answers_still_serve(tmp_path):
    d = Deadline(0)
    d.start()
    time.sleep(0.01)
    llm = CachedLLM(tmp_path / "cache.json", "example-model", "low", d)
    llm.cache[llm.key("system", "saved")] = {"ok": True}
    assert llm.ask("system", "saved", {}) == {"ok": True}
    with pytest.raises(TimeoutError):
        llm.ask("system", "new request", {})


class RecordingClient:
    """Stands in for anthropic.Anthropic: records the timeout and the request of each call."""

    def __init__(self, timeout=None, calls=None):
        self.timeout, self.calls = timeout, calls if calls is not None else []
        self.messages = self

    def with_options(self, timeout):
        return RecordingClient(timeout, self.calls)

    def stream(self, **request):
        self.calls.append((self.timeout, request))
        text = type("Text", (), {"type": "text", "text": "{}"})()
        reply = type("Reply", (), {"stop_reason": "end_turn", "content": [text],
                                   "usage": type("U", (), {"input_tokens": 0, "output_tokens": 0,
                                                           "cache_creation_input_tokens": 0,
                                                           "cache_read_input_tokens": 0})()})()
        stream = type("S", (), {"__enter__": lambda s: s, "__exit__": lambda s, *a: False,
                                "get_final_message": lambda s: reply})()
        return stream


def ask_with(deadline, tmp_path, name):
    llm = CachedLLM(tmp_path / f"{name}.json", "example-model", "low", deadline)
    llm._client = RecordingClient()
    llm.ask("system", "the same request", {})
    return llm._client.calls[0]


def test_wait_limit_only_shrinks_near_the_hard_stop_and_the_request_is_unchanged(tmp_path):
    no_deadline = ask_with(None, tmp_path, "a")
    early = Deadline(60, hard_stop=10_000)
    early.start()
    late = Deadline(60, hard_stop=90)
    late.start()
    assert no_deadline[0] is None                          # no deadline: the client's own 15-minute limit
    assert ask_with(early, tmp_path, "b")[0] == 900        # plenty of time: the same 15 minutes
    assert 10 <= ask_with(late, tmp_path, "c")[0] <= 30    # near the hard stop: a third of what is left
    assert ask_with(late, tmp_path, "d")[1] == no_deadline[1]   # what is sent never changes


def test_seconds_left_needs_a_hard_stop_and_a_started_clock():
    assert Deadline(60).seconds_left() is None
    d = Deadline(60, hard_stop=100)
    assert d.seconds_left() is None
    d.start()
    assert 99 < d.seconds_left() <= 100
