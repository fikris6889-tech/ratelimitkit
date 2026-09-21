"""Token Bucket — the algorithm that allows controlled bursts on purpose.

THE IDEA:
Each key gets an imaginary bucket that holds up to ``limit`` tokens. The
bucket refills continuously at a steady rate of ``limit / window_seconds``
tokens per second (never "all at once" — that's the fixed-window bug all
over again). Every request costs exactly 1 token:

  1. Compute how much time has passed since the bucket's state was last
     touched: ``elapsed = now - last_refill_time``.
  2. Refill: ``tokens = min(limit, tokens + elapsed * refill_rate)`` — cap
     at ``limit`` so the bucket can't overflow past its max capacity even
     if the key has been idle for hours.
  3. If ``tokens >= 1``: subtract 1, allow the request, save the new
     token count and set ``last_refill_time = now``.
     Else: block it. ``retry_after`` is how long until you'd have 1 full
     token: ``(1 - tokens) / refill_rate``.

WHY THIS ONE IS DIFFERENT FROM THE OTHER TWO:
Fixed Window and Sliding Window Log both answer "how many requests in the
last N seconds" — they're pure rate enforcement. Token Bucket answers a
subtly different question: "what's the SUSTAINED rate, while still letting
a client save up unused capacity and spend it in a burst." A client that's
been idle for a while walks in with a full bucket and can fire `limit`
requests instantly — that's a FEATURE here, not the boundary-burst bug.
This is why token bucket (or its close cousin, leaky bucket) is what you'll
find inside most real API gateways (AWS, Stripe, nginx's `limit_req` module
all use token-bucket-family algorithms) — APIs want to tolerate a client's
occasional burst of activity as long as its average rate stays sane.

THE PART PEOPLE GET WRONG:
Refilling in a background thread/timer ("every second, add N tokens to
every bucket"). Don't do this — it means every idle key still costs CPU
forever, and it doesn't compose with the ``ManualClock`` testing pattern
this kit relies on. Refill LAZILY, only inside ``check()``, computed from
elapsed wall-clock time. No timers, no background threads, no wasted work
on idle keys.

DAY 2: implemented below. ``tests/test_algorithms.py`` proves both halves
of the story on purpose: the burst behavior (a full bucket lets `limit`
requests through instantly) AND the sustained-rate behavior (once it's
empty, requests only trickle back in at exactly `refill_rate` per second,
computed lazily, with no background thread anywhere in this file).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..base import RateLimiter, RateLimitResult
from ..store import KeyedStore


@dataclass
class _BucketState:
    tokens: float
    last_refill: float


class TokenBucketLimiter(RateLimiter):
    """Allows controlled bursts, refills lazily at a steady rate. See the
    module docstring above for why that's a deliberate feature."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.store: KeyedStore[_BucketState] = KeyedStore()
        self.refill_rate = self.limit / self.window_seconds  # tokens per second

    def check(self, key: str) -> RateLimitResult:
        with self.store.locked(key) as slot:
            now = self.clock.now()
            state = slot.get_or_create(lambda: _BucketState(float(self.limit), now))

            # Lazy refill: compute how many tokens would have accumulated
            # since we last looked, cap at the bucket's capacity. No timer,
            # no background thread — an idle key costs nothing until the
            # next time it's actually checked.
            elapsed = now - state.last_refill
            state.tokens = min(self.limit, state.tokens + elapsed * self.refill_rate)
            state.last_refill = now

            if state.tokens >= 1:
                state.tokens -= 1
                slot.set(state)
                return RateLimitResult(
                    allowed=True,
                    limit=self.limit,
                    remaining=int(state.tokens),
                    retry_after=None,
                )

            slot.set(state)
            return RateLimitResult(
                allowed=False,
                limit=self.limit,
                remaining=0,
                retry_after=(1 - state.tokens) / self.refill_rate,
            )
