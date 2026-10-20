"""The time budget for the Claude steps of ingest(): the scorer allows 30 minutes for all five snapshots together."""
from __future__ import annotations

import time


class Deadline:
    def __init__(self, seconds: float, hard_stop: float | None = None):
        self.seconds = seconds
        self.hard_stop = hard_stop              # a request already sent must not wait past this (from the start)
        self.start_time: float | None = None    # set when the clock starts (the first ingest() call)
        self.end: float | None = None

    def start(self) -> None:
        if self.end is None:
            self.start_time = time.monotonic()
            self.end = self.start_time + self.seconds

    def seconds_left(self) -> float | None:
        """Seconds until the hard stop, or None when there is none (or the clock has not started)."""
        if self.hard_stop is None or self.start_time is None:
            return None
        return self.start_time + self.hard_stop - time.monotonic()

    def passed(self) -> bool:
        return self.end is not None and time.monotonic() > self.end
