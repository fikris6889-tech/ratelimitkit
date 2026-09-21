"""Fixed Window Counter — the algorithm everyone reaches for first.

THE IDEA:
Divide time into fixed-size buckets aligned to epoch/clock-start (e.g. every
60-second window: [0,60), [60,120), [120,180), ...). For each key, keep a
counter for "requests seen in the CURRENT window." When a request arrives:

  1. Figure out which window `now` falls into (hint: ``int(now // window_seconds)``
     gives you a window index that's the same for every timestamp in that window).
  2. If the stored window index != the current window index, the old window
     has expired — reset the counter to 0 and remember the new window index.
  3. If counter < limit: increment it, allow the request.
     Else: block it.

WHY THIS ONE IS TAUGHT FIRST:
O(1) memory per key (just one integer + one window index) and O(1) time.
No timestamps to store, no list to scan. It's genuinely the right choice
when you don't need precision and you have millions of keys.

THE FLAW YOU MUST UNDERSTAND (this is the whole point of building it):
Fixed windows have hard edges. A client can send `limit` requests in the
last millisecond of window N, then ANOTHER `limit` requests in the first
millisecond of window N+1. That's `2 * limit` requests inside roughly one
millisecond of real time, even though the configured limit is
"`limit` per `window_seconds`". This is called the "boundary burst"
problem. Sliding Window Log (the next file) exists specifically to fix it.
``tests/test_algorithms.py`` demonstrates this flaw on purpose, with a
``ManualClock``, so it's provable rather than just asserted in prose.

DAY 2: implemented below. If you attempted this yourself on Day 1 before
reading further — compare your version against this one. The sketch left
in the Day 1 stub is exactly this code, just no longer commented out.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..base import RateLimiter, RateLimitResult
from ..store import KeyedStore


@dataclass
class _WindowState:
    window_index: int
    count: int


class FixedWindowLimiter(RateLimiter):
    """Simplest of the three: O(1) memory/time per key, aligned windows,
    with the boundary-burst flaw described in the module docstring above."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.store: KeyedStore[_WindowState] = KeyedStore()

    def check(self, key: str) -> RateLimitResult:
        with self.store.locked(key) as slot:
            now = self.clock.now()
            current_index = int(now // self.window_seconds)
            state = slot.get_or_create(lambda: _WindowState(current_index, 0))

            if state.window_index != current_index:
                # A new window started — the old counter no longer applies,
                # no matter how large it was. This hard reset (not a decay,
                # not an interpolation) is exactly what makes boundary burst
                # possible: the counter goes from "at the limit" to "zero"
                # in a single instant.
                state.window_index = current_index
                state.count = 0

            if state.count < self.limit:
                state.count += 1
                slot.set(state)
                return RateLimitResult(
                    allowed=True,
                    limit=self.limit,
                    remaining=self.limit - state.count,
                    retry_after=None,
                )

            slot.set(state)
            window_end = (state.window_index + 1) * self.window_seconds
            return RateLimitResult(
                allowed=False,
                limit=self.limit,
                remaining=0,
                retry_after=window_end - now,
            )
