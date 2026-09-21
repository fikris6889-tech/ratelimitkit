"""The HTTP plumbing that turns any ``RateLimiter`` into a working gateway.

This is "boring" code on purpose — extracting a client key from a request,
turning a ``RateLimitResult`` into the right HTTP status code and headers,
wiring it in front of a downstream handler. None of it is the interesting
algorithm work, which is exactly why it's fully built and tested TODAY:
Day 2 is when you plug a real algorithm in and watch requests actually get
blocked and unblocked through this pipe.

Two tiny reference limiters live at the bottom of this file —
``AlwaysAllowLimiter`` and ``AlwaysDenyLimiter``. They are NOT real
algorithms (they ignore the clock and the limit entirely) — they exist
purely so this middleware and the demo server can be fully tested and run
end-to-end today, before any real algorithm from ``algorithms/`` exists.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Callable, Optional

from .base import RateLimiter, RateLimitResult

# A downstream handler just gets the already-rate-limited request and writes
# a response. It does NOT need to know rate limiting happened at all.
DownstreamHandler = Callable[[BaseHTTPRequestHandler], None]


def extract_client_key(handler: BaseHTTPRequestHandler) -> str:
    """Pick the identity a request is rate-limited by.

    Real gateways usually key on an API key or authenticated user id, with
    IP address as a fallback for anonymous traffic. We do the same: prefer
    the ``X-Client-Id`` header (so the CLI/tests can simulate many distinct
    "clients" without needing many source IPs), fall back to the TCP peer
    address.
    """
    client_id = handler.headers.get("X-Client-Id")
    if client_id:
        return client_id
    return handler.client_address[0]


def apply_rate_limit_headers(handler: BaseHTTPRequestHandler, result: RateLimitResult) -> None:
    """Set the standard-ish X-RateLimit-* headers every API gateway sends.

    These headers exist so well-behaved clients can back off BEFORE they
    get blocked, by watching ``X-RateLimit-Remaining`` drop toward zero.
    """
    handler.send_header("X-RateLimit-Limit", str(result.limit))
    handler.send_header("X-RateLimit-Remaining", str(result.remaining))
    if result.retry_after is not None:
        # Retry-After is a real, standard HTTP header (RFC 9110 §10.2.3).
        # Round UP — telling a client to retry too early just means they
        # immediately get blocked again and burn another round trip.
        import math

        handler.send_header("Retry-After", str(max(1, math.ceil(result.retry_after))))


def rate_limited(limiter: RateLimiter, downstream: DownstreamHandler) -> DownstreamHandler:
    """Wrap ``downstream`` so it only runs when ``limiter`` allows the request.

    This is the whole middleware, deliberately kept to one small function:
    check -> set headers -> either call downstream or write 429. Everything
    else in this file exists to support this one function being correct
    and testable.
    """

    def handled(handler: BaseHTTPRequestHandler) -> None:
        key = extract_client_key(handler)
        result = limiter.check(key)

        if result.allowed:
            # Let the downstream handler write its own status/body — we
            # only need to make sure the informational headers are visible.
            # We monkey-patch send_response just long enough to inject our
            # headers right after the status line, which is the only place
            # BaseHTTPRequestHandler's protocol allows extra headers to go.
            original_end_headers = handler.end_headers

            def patched_end_headers() -> None:
                apply_rate_limit_headers(handler, result)
                original_end_headers()

            handler.end_headers = patched_end_headers  # type: ignore[method-assign]
            downstream(handler)
            return

        body = json.dumps(
            {
                "error": "rate_limited",
                "message": f"Too many requests for key={key!r}. Try again shortly.",
                "retry_after_seconds": result.retry_after,
            }
        ).encode("utf-8")
        handler.send_response(429)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        apply_rate_limit_headers(handler, result)
        handler.end_headers()
        handler.wfile.write(body)

    return handled


class AlwaysAllowLimiter(RateLimiter):
    """Reference limiter used only for wiring/tests — not a real algorithm."""

    def check(self, key: str) -> RateLimitResult:
        return RateLimitResult(allowed=True, limit=self.limit, remaining=self.limit, retry_after=None)


class AlwaysDenyLimiter(RateLimiter):
    """Reference limiter used only for wiring/tests — not a real algorithm."""

    def check(self, key: str) -> RateLimitResult:
        return RateLimitResult(allowed=False, limit=self.limit, remaining=0, retry_after=self.window_seconds)
