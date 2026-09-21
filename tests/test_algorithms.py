"""Day 2's real test suite for the three algorithms.

Day 1's ``test_algorithms_stub_contract.py`` proved the algorithms failed
LOUDLY while unimplemented (see its docstring: "an unfinished algorithm
should raise NotImplementedError, not silently allow everything"). Now
that all three are implemented, that file's job is done — per its own
instructions ("once you implement an algorithm, its NotImplementedError
test here should start FAILING... delete that one test and replace it
with real behavioral tests"), it has been deleted and replaced by this
file.

Every test here uses ``ManualClock`` — never real ``time.sleep()`` — so
"advance 60 seconds" is instantaneous and 100% deterministic, exactly as
the Day 1 clock.py docstring promised it would be.
"""

from __future__ import annotations

import threading
import unittest

from ratelimitkit.algorithms.fixed_window import FixedWindowLimiter
from ratelimitkit.algorithms.sliding_window_log import SlidingWindowLogLimiter
from ratelimitkit.algorithms.token_bucket import TokenBucketLimiter
from ratelimitkit.clock import ManualClock


class TestConstructionStillValidatesBaseArguments(unittest.TestCase):
    """A real implementation is not an excuse to skip Day 1's input validation."""

    def test_fixed_window_constructs(self) -> None:
        limiter = FixedWindowLimiter(limit=5, window_seconds=10, clock=ManualClock())
        self.assertEqual(limiter.limit, 5)

    def test_sliding_window_log_constructs(self) -> None:
        limiter = SlidingWindowLogLimiter(limit=5, window_seconds=10, clock=ManualClock())
        self.assertEqual(limiter.limit, 5)

    def test_token_bucket_constructs_and_computes_refill_rate(self) -> None:
        limiter = TokenBucketLimiter(limit=10, window_seconds=5, clock=ManualClock())
        self.assertEqual(limiter.refill_rate, 2.0)  # 10 tokens / 5 seconds

    def test_all_algorithms_still_reject_bad_arguments(self) -> None:
        for cls in (FixedWindowLimiter, SlidingWindowLogLimiter, TokenBucketLimiter):
            with self.assertRaises(ValueError):
                cls(limit=0, window_seconds=10)
            with self.assertRaises(ValueError):
                cls(limit=5, window_seconds=0)


class TestFixedWindowLimiter(unittest.TestCase):
    def test_allows_up_to_limit_then_blocks(self) -> None:
        clock = ManualClock()
        limiter = FixedWindowLimiter(limit=2, window_seconds=10, clock=clock)

        r1 = limiter.check("k")
        self.assertTrue(r1.allowed)
        self.assertEqual(r1.remaining, 1)

        r2 = limiter.check("k")
        self.assertTrue(r2.allowed)
        self.assertEqual(r2.remaining, 0)

        r3 = limiter.check("k")
        self.assertFalse(r3.allowed)
        self.assertEqual(r3.remaining, 0)
        self.assertIsNotNone(r3.retry_after)

    def test_new_window_resets_the_counter(self) -> None:
        clock = ManualClock()
        limiter = FixedWindowLimiter(limit=2, window_seconds=10, clock=clock)
        limiter.check("k")
        limiter.check("k")
        self.assertFalse(limiter.check("k").allowed)

        clock.advance(10.0)  # exactly one window later
        r = limiter.check("k")
        self.assertTrue(r.allowed)
        self.assertEqual(r.remaining, 1)

    def test_retry_after_points_at_the_next_window_boundary(self) -> None:
        clock = ManualClock(start=3.0)
        limiter = FixedWindowLimiter(limit=1, window_seconds=10, clock=clock)
        limiter.check("k")  # uses the only slot in window [0, 10)
        blocked = limiter.check("k")
        self.assertFalse(blocked.allowed)
        # window ends at t=10, now is t=3 -> should wait 7s
        self.assertAlmostEqual(blocked.retry_after, 7.0)

    def test_different_keys_have_independent_counters(self) -> None:
        clock = ManualClock()
        limiter = FixedWindowLimiter(limit=1, window_seconds=10, clock=clock)
        self.assertTrue(limiter.check("alice").allowed)
        self.assertTrue(limiter.check("bob").allowed)
        self.assertFalse(limiter.check("alice").allowed)

    def test_demonstrates_the_boundary_burst_flaw_on_purpose(self) -> None:
        # This is the whole teaching point of Fixed Window: a client can
        # get 2x the configured limit through in a razor-thin slice of
        # real time, by straddling a window boundary. We PROVE it here
        # rather than just asserting it in prose.
        clock = ManualClock(start=9.999)  # last instant of window [0, 10)
        limiter = FixedWindowLimiter(limit=5, window_seconds=10, clock=clock)

        allowed_count = 0
        for _ in range(5):
            if limiter.check("k").allowed:
                allowed_count += 1
        self.assertEqual(allowed_count, 5, "should burn the full limit inside window [0,10)")

        clock.advance(0.002)  # now t=10.001 -> a NEW window, [10, 20)
        for _ in range(5):
            if limiter.check("k").allowed:
                allowed_count += 1

        # 10 requests allowed inside a ~3-millisecond stretch of real time,
        # even though the configured limit is "5 per 10 seconds". This is
        # NOT a bug in the code above -- it is the documented, well-known
        # flaw of the algorithm itself. Sliding Window Log (tested below)
        # does not have this problem.
        self.assertEqual(allowed_count, 10)

    def test_thread_safe_under_concurrent_hits_on_one_key(self) -> None:
        # Same style of proof as Day 1's KeyedStore test: hammer one key
        # from many threads and confirm the limiter never over-admits.
        clock = ManualClock()
        limiter = FixedWindowLimiter(limit=50, window_seconds=100, clock=clock)
        allowed = []
        lock = threading.Lock()

        def hit() -> None:
            result = limiter.check("shared")
            if result.allowed:
                with lock:
                    allowed.append(1)

        threads = [threading.Thread(target=hit) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(allowed), 50, "exactly `limit` requests should win the race, never more")


class TestSlidingWindowLogLimiter(unittest.TestCase):
    def test_worked_example_from_the_module_docstring(self) -> None:
        clock = ManualClock()
        limiter = SlidingWindowLogLimiter(limit=2, window_seconds=10, clock=clock)

        r1 = limiter.check("k")  # t=0
        self.assertTrue(r1.allowed)
        self.assertEqual(r1.remaining, 1)

        clock.advance(5.0)  # t=5
        r2 = limiter.check("k")
        self.assertTrue(r2.allowed)
        self.assertEqual(r2.remaining, 0)

        r3 = limiter.check("k")  # still t=5, log=[0,5], window is (-5,5]
        self.assertFalse(r3.allowed)

        clock.advance(5.1)  # t=10.1, cutoff=0.1 -> t=0 ages out
        r4 = limiter.check("k")
        self.assertTrue(r4.allowed)

    def test_never_allows_more_than_limit_in_any_rolling_window(self) -> None:
        # The exactness property, proven directly: no matter WHEN we look,
        # a trailing window of `window_seconds` never contains more than
        # `limit` allowed hits. This includes straddling where a Fixed
        # Window boundary would have been -- that's the whole point of
        # this algorithm existing.
        clock = ManualClock()
        limiter = SlidingWindowLogLimiter(limit=5, window_seconds=10, clock=clock)
        allowed_timestamps = []

        # Hammer it constantly for 30 "seconds" of simulated time, checking
        # every 0.5s, including straight across where fixed windows [0,10),
        # [10,20) would reset a naive counter to zero.
        t = 0.0
        while t <= 30.0:
            clock.set(t)
            result = limiter.check("k")
            if result.allowed:
                allowed_timestamps.append(t)
            t += 0.5

        # Check every possible 10-second trailing window and confirm it
        # never contains more than `limit` allowed timestamps.
        for end in allowed_timestamps:
            start = end - 10.0
            count_in_window = sum(1 for ts in allowed_timestamps if start < ts <= end)
            self.assertLessEqual(
                count_in_window,
                5,
                f"window ending at t={end} contained {count_in_window} requests, expected <= 5",
            )

    def test_retry_after_matches_when_the_oldest_entry_ages_out(self) -> None:
        clock = ManualClock()
        limiter = SlidingWindowLogLimiter(limit=1, window_seconds=10, clock=clock)
        limiter.check("k")  # t=0, log=[0]
        clock.set(4.0)
        blocked = limiter.check("k")
        self.assertFalse(blocked.allowed)
        # oldest entry (t=0) ages out at t=10 -> 6s from now
        self.assertAlmostEqual(blocked.retry_after, 6.0)

    def test_thread_safe_under_concurrent_hits_on_one_key(self) -> None:
        clock = ManualClock()
        limiter = SlidingWindowLogLimiter(limit=50, window_seconds=100, clock=clock)
        allowed = []
        lock = threading.Lock()

        def hit() -> None:
            result = limiter.check("shared")
            if result.allowed:
                with lock:
                    allowed.append(1)

        threads = [threading.Thread(target=hit) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(allowed), 50)


class TestTokenBucketLimiter(unittest.TestCase):
    def test_worked_example_from_the_module_docstring(self) -> None:
        clock = ManualClock()
        limiter = TokenBucketLimiter(limit=5, window_seconds=10, clock=clock)  # 0.5 tok/s

        for _ in range(5):
            self.assertTrue(limiter.check("k").allowed)

        self.assertFalse(limiter.check("k").allowed)  # bucket empty

        clock.advance(2.0)  # 2s * 0.5 tok/s = 1.0 token refilled
        self.assertTrue(limiter.check("k").allowed)  # exactly 1 token available

    def test_burst_is_allowed_when_bucket_is_full(self) -> None:
        # This is Token Bucket's defining, deliberate feature: an idle
        # client can spend its whole allowance in one instant.
        clock = ManualClock()
        limiter = TokenBucketLimiter(limit=10, window_seconds=10, clock=clock)
        results = [limiter.check("k") for _ in range(10)]
        self.assertTrue(all(r.allowed for r in results))
        self.assertFalse(limiter.check("k").allowed)

    def test_sustained_rate_after_bucket_is_drained(self) -> None:
        clock = ManualClock()
        limiter = TokenBucketLimiter(limit=1, window_seconds=1, clock=clock)  # 1 tok/s
        limiter.check("k")  # drains the single starting token
        self.assertFalse(limiter.check("k").allowed)

        clock.advance(0.5)
        self.assertFalse(limiter.check("k").allowed, "only half a token available so far")

        clock.advance(0.5)  # total 1.0s elapsed since last refill point
        self.assertTrue(limiter.check("k").allowed)

    def test_refill_never_exceeds_capacity_even_after_a_long_idle_period(self) -> None:
        clock = ManualClock()
        limiter = TokenBucketLimiter(limit=3, window_seconds=3, clock=clock)  # 1 tok/s
        limiter.check("k")  # tokens: 3 -> 2
        clock.advance(1000.0)  # idle for a very long time
        results = [limiter.check("k") for _ in range(3)]
        self.assertTrue(all(r.allowed for r in results), "bucket should cap at `limit`, not overflow")
        self.assertFalse(limiter.check("k").allowed, "a 4th immediate request should still be blocked")

    def test_retry_after_matches_time_to_next_full_token(self) -> None:
        clock = ManualClock()
        limiter = TokenBucketLimiter(limit=2, window_seconds=10, clock=clock)  # 0.2 tok/s
        limiter.check("k")
        limiter.check("k")  # bucket now at 0 tokens
        blocked = limiter.check("k")
        self.assertFalse(blocked.allowed)
        self.assertAlmostEqual(blocked.retry_after, 5.0)  # 1 token / 0.2 tok/s = 5s

    def test_thread_safe_under_concurrent_hits_on_one_key(self) -> None:
        clock = ManualClock()
        limiter = TokenBucketLimiter(limit=50, window_seconds=100, clock=clock)
        allowed = []
        lock = threading.Lock()

        def hit() -> None:
            result = limiter.check("shared")
            if result.allowed:
                with lock:
                    allowed.append(1)

        threads = [threading.Thread(target=hit) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(allowed), 50)


if __name__ == "__main__":
    unittest.main()
