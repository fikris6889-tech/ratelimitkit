"""The three real rate limiting algorithms in this kit.

Each module defines one ``RateLimiter`` subclass, fully implemented and
tested as of Day 2:

- ``fixed_window.py``       — FixedWindowLimiter: simplest, has a boundary-burst flaw
- ``sliding_window_log.py`` — SlidingWindowLogLimiter: exact, more memory
- ``token_bucket.py``       — TokenBucketLimiter: allows controlled bursts

Every module docstring still carries the full algorithm explanation,
tradeoffs, and worked example it had on Day 1 — implementing the logic
didn't remove the teaching, it just replaced the ``NotImplementedError``
with the real thing. See ``tests/test_algorithms.py`` for the behavioral
proof of each one (including a direct demonstration of Fixed Window's
boundary-burst flaw and Sliding Window Log NOT having it, side by side).
"""
