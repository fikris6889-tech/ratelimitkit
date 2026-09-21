"""Sliding Window Log — exact, at the cost of memory.

THE IDEA:
For each key, keep a log (a ``collections.deque`` is ideal — O(1) pops from
the left) of the exact timestamp of every request in roughly the last
``window_seconds``. When a request arrives:

  1. Drop every timestamp older than ``now - window_seconds`` from the
     front of the deque (they've aged out — this is why a deque beats a
     list here: popping from the front of a list is O(n), a deque is O(1)).
  2. If ``len(deque) < limit``: append `now`, allow the request.
     Else: block it. The oldest timestamp still in the deque tells you
     exactly when a slot frees up — that's your ``retry_after``.

WHY THIS FIXES FIXED WINDOW'S FLAW:
There are no aligned window boundaries at all — "the window" is always
"the last `window_seconds`, measured from right now." A client literally
cannot get more than `limit` requests through in ANY rolling
`window_seconds`-long stretch of time, boundary or no boundary. This is
the "exact" algorithm — it enforces the limit with zero slack, which is
also its downside:

THE TRADEOFF YOU MUST UNDERSTAND:
Memory is O(limit) per key, not O(1) — you're storing one timestamp per
request currently inside the window. For a generous limit (say, 10,000
requests/hour) across many keys, that adds up. This is exactly the kind of
"correct but expensive" baseline that motivates Sliding Window COUNTER (an
approximation that interpolates between two fixed windows instead of
storing a log) — mentioned in the blog as a stretch goal, not required for
this project, but worth knowing exists.

DAY 2: implemented below, and ``tests/test_algorithms.py`` proves the exact
property directly: hammer this limiter with more than `limit` requests
inside any rolling window, in any pattern (including right across where a
Fixed Window boundary WOULD have been), and it never once allows more than
`limit` through. That's the head-to-head comparison the Day 1 post
promised.
"""

from __future__ import annotations

from collections import deque
from typing import Deque

from ..base import RateLimiter, RateLimitResult
from ..store import KeyedStore


class SlidingWindowLogLimiter(RateLimiter):
    """Exact rate enforcement, O(limit) memory per key. See the module
    docstring above for the full tradeoff discussion."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.store: KeyedStore[Deque[float]] = KeyedStore()

    def check(self, key: str) -> RateLimitResult:
        with self.store.locked(key) as slot:
            now = self.clock.now()
            log = slot.get_or_create(deque)
            cutoff = now - self.window_seconds

            # Age out everything that fell outside the rolling window. A
            # deque makes this O(k) in the number of entries actually
            # expired, not O(n) in the whole log, because we only ever pop
            # from the front.
            while log and log[0] <= cutoff:
                log.popleft()

            if len(log) < self.limit:
                log.append(now)
                slot.set(log)
                return RateLimitResult(
                    allowed=True,
                    limit=self.limit,
                    remaining=self.limit - len(log),
                    retry_after=None,
                )

            # Blocked: the log is full. The OLDEST entry still inside the
            # window is the one that will age out soonest — the moment it
            # crosses `cutoff`, a slot opens up. That's exactly `retry_after`.
            slot.set(log)
            return RateLimitResult(
                allowed=False,
                limit=self.limit,
                remaining=0,
                retry_after=log[0] - cutoff,
            )
