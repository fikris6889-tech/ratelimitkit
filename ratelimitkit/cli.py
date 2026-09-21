"""A tiny concurrent load-tester for the demo gateway.

Fires ``--requests`` requests at a running ``server.py`` instance using a
thread pool, and reports how many were allowed (200) vs. blocked (429).
Useful today (to sanity-check the middleware's wiring end-to-end against
``AlwaysAllowLimiter``/``AlwaysDenyLimiter``) and even more useful
tomorrow, once a real algorithm is behind the gateway — you'll be able to
literally watch the pass/block counts match the math of whichever
algorithm you plugged in.
"""

from __future__ import annotations

import argparse
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def fire_one(url: str, client_id: str) -> int:
    """Send one GET request, return the HTTP status code (or -1 on connection failure)."""
    req = urllib.request.Request(url, headers={"X-Client-Id": client_id})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except urllib.error.URLError:
        return -1


def run(url: str, num_requests: int, num_clients: int, concurrency: int) -> Counter:
    clients = [f"load-test-client-{i}" for i in range(num_clients)]
    results: Counter = Counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(fire_one, url, clients[i % num_clients]) for i in range(num_requests)
        ]
        for future in futures:
            results[future.result()] += 1
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Load-test the ratelimitkit demo gateway")
    parser.add_argument("--url", default="http://127.0.0.1:8080/orders")
    parser.add_argument("--requests", type=int, default=20, dest="num_requests")
    parser.add_argument("--clients", type=int, default=1, dest="num_clients", help="distinct X-Client-Id values to spread requests across")
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    results = run(args.url, args.num_requests, args.num_clients, args.concurrency)
    total = sum(results.values())
    allowed = results.get(200, 0)
    blocked = results.get(429, 0)
    failed = total - allowed - blocked

    print(f"Sent {total} requests across {args.num_clients} client id(s):")
    print(f"  200 allowed : {allowed}")
    print(f"  429 blocked : {blocked}")
    if failed:
        print(f"  other/failed: {failed}  (statuses seen: {dict(results)})")


if __name__ == "__main__":
    main()
