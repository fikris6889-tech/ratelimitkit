"""Thread-safe per-key state, without one giant lock strangling every request.

Every algorithm needs to keep *some* mutable state per key (a counter, a
list of timestamps, a token count + last-refill time). The naive approach —
one dict, one global ``threading.Lock`` around every read/write — works,
but it means a request for key "alice" blocks behind a request for
completely unrelated key "bob". Under real load, that global lock becomes
the bottleneck, not the algorithm.

``KeyedStore`` fixes this the standard way: a lock *per key* (created
lazily, on first use), so unrelated keys never block each other, while
same-key access is still fully serialized (which is exactly the safety
property the algorithms need).
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, Generic, TypeVar

T = TypeVar("T")


class KeyedStore(Generic[T]):
    """A dict of per-key values, each guarded by its own lock.

    Usage pattern every algorithm follows:

        with store.locked(key) as slot:
            state = slot.get_or_create(factory)
            # ... read/mutate `state` freely, you hold the per-key lock ...
            slot.set(state)
    """

    def __init__(self) -> None:
        self._values: Dict[str, T] = {}
        self._locks: Dict[str, threading.Lock] = {}
        # Guards the _locks dict itself (creating a new per-key lock).
        # This is the ONLY lock ever held by more than one key's worth of
        # work, and it's held only for the few nanoseconds it takes to
        # look up/insert a dict entry — never while doing algorithm work.
        self._admin_lock = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._admin_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def locked(self, key: str) -> "_Slot[T]":
        """Return a context manager that holds ``key``'s lock for its duration."""
        return _Slot(self, key)

    def __len__(self) -> int:
        return len(self._values)


class _Slot(Generic[T]):
    """Context manager handed out by ``KeyedStore.locked()``.

    Kept as its own class (rather than a generator + @contextmanager) so
    that ``get_or_create``/``get``/``set`` are plain, easy-to-read methods
    inside the `with` block.
    """

    def __init__(self, store: KeyedStore[T], key: str) -> None:
        self._store = store
        self._key = key
        self._lock = store._lock_for(key)

    def __enter__(self) -> "_Slot[T]":
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._lock.release()

    def get(self) -> T | None:
        return self._store._values.get(self._key)

    def get_or_create(self, factory: Callable[[], T]) -> T:
        value = self._store._values.get(self._key)
        if value is None:
            value = factory()
            self._store._values[self._key] = value
        return value

    def set(self, value: T) -> None:
        self._store._values[self._key] = value
