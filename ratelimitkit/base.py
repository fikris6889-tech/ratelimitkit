"""The contract every rate limiting algorithm has to satisfy.

Three algorithms (fixed window, sliding window log, token bucket) are going
to live under ``ratelimitkit/algorithms/``. They behave very differently
internally, but from the outside — from the middleware's point of view —
they all need to answer exactly one question the exact same way:

    "Given this key, right now, am I allowed through — and if not, how
    long until I am?"

That question/answer shape is ``RateLimiter.check() -> RateLimitResult``.
Nail this interface down first (today) and the algorithms you write
tomorrow are drop-in interchangeable with each other and with the
middleware — you can swap Token Bucket for Sliding Window Log in the demo
server by changing one line.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .clock import Clock, RealClock


@dataclass(frozen=True)
class RateLimitResult:
    """The answer to "should this request go through?"

    Attributes:
        allowed: True if the request should proceed.
        limit: The configured limit (requests per window), echoed back so
            callers/middleware can set informational headers.
        remaining: How many more requests this key could make right now
            without being blocked. Always >= 0. When ``allowed`` is False
            this is 0.
        retry_after: Seconds the caller should wait before trying again.
            None when ``allowed`` is True (no need to wait).
    """

    allowed: bool
    limit: int
    remaining: int
    retry_after: Optional[float]

    def __post_init__(self) -> None:
        if self.remaining < 0:
            raise ValueError("remaining can't be negative")
        if self.allowed and self.retry_after is not None:
            raise ValueError("an allowed result should not carry a retry_after")
        if not self.allowed and self.remaining != 0:
            raise ValueError("a blocked result must report remaining=0")


class RateLimiter(ABC):
    """Base class for every algorithm in this kit.

    Implementations MUST be thread-safe: ``check()`` will be called
    concurrently, from multiple worker threads in the demo HTTP server,
    often for the SAME key (that's the whole point of rate limiting a busy
    client). If two threads both check the same key at the same instant,
    at most one of them should ever "use up" the same slot.

    Implementations MUST NOT block or sleep inside ``check()`` — a rate
    limiter that makes requests slower while they're waiting to be
    rate-limited has defeated its own purpose. Decide instantly; the
    ``retry_after`` field is how you tell the *caller* to wait, not how
    you make them wait.
    """

    def __init__(self, limit: int, window_seconds: float, clock: Optional[Clock] = None) -> None:
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = float(window_seconds)
        self.clock: Clock = clock if clock is not None else RealClock()

    @abstractmethod
    def check(self, key: str) -> RateLimitResult:
        """Decide whether the request identified by ``key`` may proceed.

        ``key`` is caller-defined — could be a client IP, an API key, a
        user ID, or a compound string like ``"user:42:POST:/orders"`` if
        you want per-route limits. This base class and the middleware
        don't care what it means, only that it's a stable string identity
        for "the thing being rate limited."
        """
        raise NotImplementedError
