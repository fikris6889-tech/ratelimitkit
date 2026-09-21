"""Time, made swappable.

Every rate limiting algorithm is really just "arithmetic over timestamps."
That means every algorithm's unit tests are only as good as your ability to
control time. If your tests rely on ``time.sleep()`` to make windows expire,
they will be slow AND flaky (a slow CI runner can make a "1 second window"
test fail for reasons that have nothing to do with your logic).

The fix is a tiny abstraction: every limiter takes a ``Clock`` instead of
calling ``time.monotonic()`` directly. In production you pass ``RealClock()``.
In tests you pass ``ManualClock()`` and advance it by exact amounts — a
"window expires after 60s" test becomes instantaneous and 100% deterministic.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod


class Clock(ABC):
    """Anything that can report "now" as a float number of seconds.

    Must be monotonic (never go backwards) — every algorithm in this kit
    assumes ``now()`` only increases, exactly like ``time.monotonic()``.
    """

    @abstractmethod
    def now(self) -> float:
        raise NotImplementedError


class RealClock(Clock):
    """Wraps ``time.monotonic()``. Use this in production and in the demo server."""

    def now(self) -> float:
        return time.monotonic()


class ManualClock(Clock):
    """A fake clock you control by hand. Use this in every algorithm test.

    Example:
        clock = ManualClock(start=0.0)
        limiter = TokenBucketLimiter(limit=5, window_seconds=10, clock=clock)
        clock.advance(10.0)   # pretend 10 real seconds passed, instantly
    """

    def __init__(self, start: float = 0.0) -> None:
        if start < 0:
            raise ValueError("start must be >= 0")
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError(
                "ManualClock can't go backwards (real clocks can't either — "
                "that's the whole point of testing against this abstraction)"
            )
        self._now += seconds

    def set(self, value: float) -> None:
        if value < self._now:
            raise ValueError("ManualClock can't be set backwards")
        self._now = value
