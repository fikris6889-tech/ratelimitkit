"""RateLimitKit — a small, dependency-free library of rate limiting algorithms,
plus a demo HTTP middleware/gateway that uses them.

Day 2 of 2 (Daily Coding Teaching Series): all three algorithms under
``ratelimitkit/algorithms/`` — Fixed Window, Sliding Window Log, Token
Bucket — are now fully implemented and tested, and the demo gateway
(``server.py``) runs a real one by default (``--algorithm token``, with
``fixed``/``sliding``/``allow``/``deny`` also selectable). Day 1 built and
tested everything else: the clock abstraction, the thread-safe storage
layer, the base interface, and the HTTP middleware.
"""

from .base import RateLimiter, RateLimitResult
from .clock import Clock, RealClock, ManualClock
from .store import KeyedStore

__all__ = [
    "RateLimiter",
    "RateLimitResult",
    "Clock",
    "RealClock",
    "ManualClock",
    "KeyedStore",
]
