import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from ratelimitkit.algorithms.fixed_window import FixedWindowLimiter
from ratelimitkit.algorithms.sliding_window_log import SlidingWindowLogLimiter
from ratelimitkit.algorithms.token_bucket import TokenBucketLimiter
from ratelimitkit.middleware import AlwaysAllowLimiter, AlwaysDenyLimiter
from ratelimitkit.server import build_limiter, make_handler_class


class _Args:
    """Minimal stand-in for argparse.Namespace, just the fields build_limiter reads."""

    def __init__(self, algorithm: str = "token", limit: int = 5, window: float = 10.0) -> None:
        self.algorithm = algorithm
        self.limit = limit
        self.window = window


def _start_server(limiter):
    handler_cls = make_handler_class(limiter)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


class TestMiddlewareEndToEnd(unittest.TestCase):
    def test_health_endpoint_bypasses_rate_limiting(self) -> None:
        server, thread, port = _start_server(AlwaysDenyLimiter(limit=1, window_seconds=10))
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(json.loads(resp.read())["status"], "ok")
        finally:
            server.shutdown()
            thread.join(timeout=5)

    def test_allowed_request_passes_through_with_headers(self) -> None:
        server, thread, port = _start_server(AlwaysAllowLimiter(limit=5, window_seconds=10))
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/orders", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.headers.get("X-RateLimit-Limit"), "5")
                self.assertEqual(resp.headers.get("X-RateLimit-Remaining"), "5")
                self.assertIsNone(resp.headers.get("Retry-After"))
                body = json.loads(resp.read())
                self.assertIn("orders", body)
        finally:
            server.shutdown()
            thread.join(timeout=5)

    def test_blocked_request_returns_429_with_retry_after(self) -> None:
        server, thread, port = _start_server(AlwaysDenyLimiter(limit=3, window_seconds=7))
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/orders")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            err = ctx.exception
            self.assertEqual(err.code, 429)
            self.assertEqual(err.headers.get("X-RateLimit-Remaining"), "0")
            self.assertEqual(err.headers.get("Retry-After"), "7")
            body = json.loads(err.read())
            self.assertEqual(body["error"], "rate_limited")
        finally:
            server.shutdown()
            thread.join(timeout=5)

    def test_client_id_header_is_used_as_the_rate_limit_key(self) -> None:
        # AlwaysAllowLimiter ignores the key, but this test locks in the
        # extraction behavior middleware.extract_client_key relies on —
        # important because Day 2's real algorithms DO care which key they see.
        from ratelimitkit.middleware import extract_client_key

        class _Headers(dict):
            def get(self, key, default=None):
                return dict.get(self, key, default)

        class Handler:
            def __init__(self, header_value):
                self.headers = _Headers({"X-Client-Id": header_value} if header_value else {})
                self.client_address = ("10.0.0.5", 12345)

        self.assertEqual(extract_client_key(Handler("alice")), "alice")
        self.assertEqual(extract_client_key(Handler(None)), "10.0.0.5")

    def test_real_algorithm_actually_blocks_over_real_sockets(self) -> None:
        # Day 1 could only prove the *pipe* worked, with fake reference
        # limiters. Day 2's payoff: a REAL algorithm, wired through the
        # exact same middleware, over a real ThreadingHTTPServer, blocking
        # for real once its limit is exhausted.
        server, thread, port = _start_server(TokenBucketLimiter(limit=2, window_seconds=100))
        try:
            url = f"http://127.0.0.1:{port}/orders"
            statuses = []
            for _ in range(3):
                req = urllib.request.Request(url, headers={"X-Client-Id": "same-client"})
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        statuses.append(resp.status)
                except urllib.error.HTTPError as e:
                    statuses.append(e.code)
            # bucket starts with 2 tokens: 200, 200, then empty -> 429
            self.assertEqual(statuses, [200, 200, 429])
        finally:
            server.shutdown()
            thread.join(timeout=5)


class TestBuildLimiter(unittest.TestCase):
    def test_default_selects_token_bucket(self) -> None:
        # Day 2: the demo gateway now defaults to a REAL algorithm, not a
        # reference stand-in — this is the "one-line swap" Day 1 promised.
        limiter = build_limiter(_Args())
        self.assertIsInstance(limiter, TokenBucketLimiter)

    def test_algorithm_deny_selects_always_deny(self) -> None:
        limiter = build_limiter(_Args(algorithm="deny"))
        self.assertIsInstance(limiter, AlwaysDenyLimiter)

    def test_algorithm_allow_selects_always_allow(self) -> None:
        limiter = build_limiter(_Args(algorithm="allow"))
        self.assertIsInstance(limiter, AlwaysAllowLimiter)

    def test_algorithm_fixed_selects_fixed_window(self) -> None:
        limiter = build_limiter(_Args(algorithm="fixed"))
        self.assertIsInstance(limiter, FixedWindowLimiter)

    def test_algorithm_sliding_selects_sliding_window_log(self) -> None:
        limiter = build_limiter(_Args(algorithm="sliding"))
        self.assertIsInstance(limiter, SlidingWindowLogLimiter)

    def test_algorithm_token_selects_token_bucket(self) -> None:
        limiter = build_limiter(_Args(algorithm="token"))
        self.assertIsInstance(limiter, TokenBucketLimiter)

    def test_unknown_algorithm_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_limiter(_Args(algorithm="quantum"))


if __name__ == "__main__":
    unittest.main()
