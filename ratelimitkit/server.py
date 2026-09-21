"""A tiny demo API gateway, fronted by the rate limit middleware.

Run it, hit it with curl or ``cli.py``, watch ``X-RateLimit-*`` headers and
429s. Day 1 wired this to ``AlwaysAllowLimiter``/``AlwaysDenyLimiter``
because no real algorithm existed yet. Day 2: the promised one-line swap
has arrived — ``build_limiter()`` below now instantiates whichever real
algorithm ``--algorithm`` selects (``token`` bucket is the default, since
it's the one most real-world API gateways reach for), and that one-line
swap is the entire payoff of having built the ``RateLimiter`` interface
first, on Day 1, before any algorithm existed.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .base import RateLimiter
from .middleware import AlwaysAllowLimiter, AlwaysDenyLimiter, rate_limited

ALGORITHM_CHOICES = ("token", "sliding", "fixed", "allow", "deny")


def fake_orders_endpoint(handler: BaseHTTPRequestHandler) -> None:
    """Stand-in for "the real API." Rate limiting shouldn't care what this does."""
    body = json.dumps({"orders": [], "served_by": "ratelimitkit-demo"}).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def build_limiter(args: argparse.Namespace) -> RateLimiter:
    """Turn parsed CLI args into a real ``RateLimiter``.

    This is the one-line-per-algorithm swap Day 1 promised: every branch
    below constructs a limiter with the exact same ``(limit, window_seconds)``
    shape, because that's the whole payoff of nailing the ``RateLimiter``
    interface down before any algorithm existed.
    """
    algorithm = getattr(args, "algorithm", "token")

    if algorithm == "deny":
        return AlwaysDenyLimiter(limit=args.limit, window_seconds=args.window)
    if algorithm == "allow":
        return AlwaysAllowLimiter(limit=args.limit, window_seconds=args.window)
    if algorithm == "fixed":
        from .algorithms.fixed_window import FixedWindowLimiter

        return FixedWindowLimiter(limit=args.limit, window_seconds=args.window)
    if algorithm == "sliding":
        from .algorithms.sliding_window_log import SlidingWindowLogLimiter

        return SlidingWindowLogLimiter(limit=args.limit, window_seconds=args.window)
    if algorithm == "token":
        from .algorithms.token_bucket import TokenBucketLimiter

        return TokenBucketLimiter(limit=args.limit, window_seconds=args.window)

    raise ValueError(f"unknown algorithm: {algorithm!r}")


def make_handler_class(limiter: RateLimiter) -> type:
    guarded = rate_limited(limiter, fake_orders_endpoint)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (stdlib naming convention)
            if self.path == "/health":
                body = b'{"status": "ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            guarded(self)

        def log_message(self, fmt: str, *fmt_args) -> None:  # quieter test/demo output
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="RateLimitKit demo gateway")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--limit", type=int, default=5, help="requests per window")
    parser.add_argument("--window", type=float, default=10.0, help="window size in seconds")
    parser.add_argument(
        "--algorithm",
        choices=ALGORITHM_CHOICES,
        default="token",
        help="which limiter to run behind the gateway (default: token, a real algorithm)",
    )
    parser.add_argument(
        "--deny",
        action="store_true",
        help="shorthand for --algorithm deny (kept for Day 1 compatibility)",
    )
    args = parser.parse_args()
    if args.deny:
        args.algorithm = "deny"

    limiter = build_limiter(args)
    handler_cls = make_handler_class(limiter)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_cls)
    print(f"ratelimitkit demo gateway on http://127.0.0.1:{args.port}  (limiter={type(limiter).__name__})")
    print("try: curl -i http://127.0.0.1:%d/orders" % args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
