import unittest

from ratelimitkit.clock import ManualClock, RealClock


class TestManualClock(unittest.TestCase):
    def test_starts_at_zero_by_default(self) -> None:
        self.assertEqual(ManualClock().now(), 0.0)

    def test_starts_at_given_value(self) -> None:
        self.assertEqual(ManualClock(start=42.0).now(), 42.0)

    def test_rejects_negative_start(self) -> None:
        with self.assertRaises(ValueError):
            ManualClock(start=-1.0)

    def test_advance_moves_time_forward(self) -> None:
        clock = ManualClock()
        clock.advance(5.0)
        clock.advance(2.5)
        self.assertEqual(clock.now(), 7.5)

    def test_advance_rejects_negative(self) -> None:
        clock = ManualClock()
        with self.assertRaises(ValueError):
            clock.advance(-1.0)

    def test_set_moves_to_exact_value(self) -> None:
        clock = ManualClock()
        clock.set(100.0)
        self.assertEqual(clock.now(), 100.0)

    def test_set_rejects_going_backwards(self) -> None:
        clock = ManualClock(start=10.0)
        with self.assertRaises(ValueError):
            clock.set(5.0)


class TestRealClock(unittest.TestCase):
    def test_now_is_monotonic_non_decreasing(self) -> None:
        clock = RealClock()
        a = clock.now()
        b = clock.now()
        self.assertGreaterEqual(b, a)

    def test_now_returns_a_float(self) -> None:
        self.assertIsInstance(RealClock().now(), float)


if __name__ == "__main__":
    unittest.main()
