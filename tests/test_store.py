import threading
import unittest

from ratelimitkit.store import KeyedStore


class TestKeyedStore(unittest.TestCase):
    def test_get_on_missing_key_returns_none(self) -> None:
        store: KeyedStore[int] = KeyedStore()
        with store.locked("k") as slot:
            self.assertIsNone(slot.get())

    def test_get_or_create_calls_factory_once(self) -> None:
        store: KeyedStore[list] = KeyedStore()
        calls = []

        def factory():
            calls.append(1)
            return []

        with store.locked("k") as slot:
            slot.get_or_create(factory)
        with store.locked("k") as slot:
            slot.get_or_create(factory)

        self.assertEqual(len(calls), 1, "factory should only run on first access")

    def test_set_then_get_round_trips(self) -> None:
        store: KeyedStore[str] = KeyedStore()
        with store.locked("k") as slot:
            slot.set("hello")
        with store.locked("k") as slot:
            self.assertEqual(slot.get(), "hello")

    def test_different_keys_are_independent(self) -> None:
        store: KeyedStore[int] = KeyedStore()
        with store.locked("a") as slot:
            slot.set(1)
        with store.locked("b") as slot:
            slot.set(2)
        with store.locked("a") as slot:
            self.assertEqual(slot.get(), 1)
        with store.locked("b") as slot:
            self.assertEqual(slot.get(), 2)

    def test_len_reflects_number_of_keys_ever_set(self) -> None:
        store: KeyedStore[int] = KeyedStore()
        with store.locked("a") as slot:
            slot.set(1)
        with store.locked("b") as slot:
            slot.set(2)
        self.assertEqual(len(store), 2)

    def test_same_key_lock_is_reused_not_recreated(self) -> None:
        store: KeyedStore[int] = KeyedStore()
        lock1 = store._lock_for("k")
        lock2 = store._lock_for("k")
        self.assertIs(lock1, lock2)

    def test_concurrent_increments_on_same_key_are_not_lost(self) -> None:
        # This is the whole point of the per-key lock: 200 threads all doing
        # a read-modify-write on the SAME key must not lose updates to a
        # race condition. If locking were broken, this count would come out
        # less than 200 nearly every run.
        store: KeyedStore[int] = KeyedStore()

        def increment() -> None:
            with store.locked("shared") as slot:
                current = slot.get_or_create(lambda: 0)
                slot.set(current + 1)

        threads = [threading.Thread(target=increment) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        with store.locked("shared") as slot:
            self.assertEqual(slot.get(), 200)

    def test_concurrent_access_to_different_keys_does_not_deadlock(self) -> None:
        store: KeyedStore[int] = KeyedStore()

        def touch(key: str) -> None:
            for _ in range(50):
                with store.locked(key) as slot:
                    slot.set(slot.get_or_create(lambda: 0) + 1)

        keys = [f"key-{i}" for i in range(20)]
        threads = [threading.Thread(target=touch, args=(k,)) for k in keys]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        for t in threads:
            self.assertFalse(t.is_alive(), "a thread appears to have deadlocked")


if __name__ == "__main__":
    unittest.main()
