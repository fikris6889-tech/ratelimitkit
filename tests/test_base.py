import unittest

from ratelimitkit.base import RateLimiter, RateLimitResult
from ratelimitkit.clock import ManualClock


class TestRateLimitResult(unittest.TestCase):
    def test_valid_allowed_result(self) -> None:
        r = RateLimitResult(allowed=True, limit=5, remaining=3, retry_after=None)
        self.assertTrue(r.allowed)

    def test_valid_blocked_result(self) -> None:
        r = RateLimitResult(allowed=False, limit=5, remaining=0, retry_after=1.5)
        self.assertFalse(r.allowed)

    def test_negative_remaining_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RateLimitResult(allowed=True, limit=5, remaining=-1, retry_after=None)

    def test_allowed_with_retry_after_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RateLimitResult(allowed=True, limit=5, remaining=3, retry_after=2.0)

    def test_blocked_with_nonzero_remaining_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RateLimitResult(allowed=False, limit=5, remaining=1, retry_after=2.0)

    def test_is_frozen(self) -> None:
        r = RateLimitResult(allowed=True, limit=5, remaining=3, retry_after=None)
        with self.assertRaises(Exception):
            r.allowed = False  # type: ignore[misc]


class _DummyLimiter(RateLimiter):
    """Smallest possible concrete subclass, for testing the base class itself."""

    def check(self, key: str) -> RateLimitResult:
        return RateLimitResult(allowed=True, limit=self.limit, remaining=self.limit, retry_after=None)


class TestRateLimiterBase(unittest.TestCase):
    def test_rejects_zero_limit(self) -> None:
        with self.assertRaises(ValueError):
            _DummyLimiter(limit=0, window_seconds=10)

    def test_rejects_negative_limit(self) -> None:
        with self.assertRaises(ValueError):
            _DummyLimiter(limit=-5, window_seconds=10)

    def test_rejects_zero_window(self) -> None:
        with self.assertRaises(ValueError):
            _DummyLimiter(limit=5, window_seconds=0)

    def test_rejects_negative_window(self) -> None:
        with self.assertRaises(ValueError):
            _DummyLimiter(limit=5, window_seconds=-1)

    def test_defaults_to_real_clock_when_none_given(self) -> None:
        limiter = _DummyLimiter(limit=5, window_seconds=10)
        # RealClock().now() should behave like a float timestamp
        self.assertIsInstance(limiter.clock.now(), float)

    def test_uses_provided_clock(self) -> None:
        clock = ManualClock(start=99.0)
        limiter = _DummyLimiter(limit=5, window_seconds=10, clock=clock)
        self.assertEqual(limiter.clock.now(), 99.0)

    def test_cannot_instantiate_abstract_base_directly(self) -> None:
        with self.assertRaises(TypeError):
            RateLimiter(limit=5, window_seconds=10)  # type: ignore[abstract]


if __name__ == "__main__":
    unittest.main()
