# RateLimitKit — a teaching build of three rate limiting algorithms

Intermediate-tier project for the Daily Coding Teaching Series. **Day 2 of 2:
final build — all three algorithms implemented, tested, and wired live.**

RateLimitKit is a small, dependency-free Python library implementing three
classic rate limiting algorithms (Fixed Window, Sliding Window Log, Token
Bucket) behind one common interface, plus a demo HTTP API gateway and a
concurrent load-testing CLI that use whichever algorithm you plug in.

## Status: Day 2 — COMPLETE

- **Day 1 (plumbing — unchanged):** the swappable clock abstraction
  (`clock.py`), the thread-safe per-key storage layer (`store.py`), the
  `RateLimiter`/`RateLimitResult` contract (`base.py`), the HTTP middleware
  that turns any limiter into 429s + `X-RateLimit-*` headers
  (`middleware.py`), the demo gateway (`server.py`), and the concurrent
  load-test CLI (`cli.py`).
- **Day 2 (today — the actual algorithms):** `FixedWindowLimiter`,
  `SlidingWindowLogLimiter`, and `TokenBucketLimiter` are fully implemented
  in `ratelimitkit/algorithms/`, each proven against a real behavioral test
  suite (`tests/test_algorithms.py`, 20 tests) — including a direct,
  on-purpose demonstration of Fixed Window's boundary-burst flaw, a proof
  that Sliding Window Log never exceeds its limit in ANY rolling window,
  and both the burst and sustained-rate halves of Token Bucket's story.
  All three also have a dedicated 200-thread concurrency test proving
  thread-safety under real contention on one key.
- **The demo gateway now runs a real algorithm by default:** `server.py`
  defaults to `--algorithm token` (Token Bucket), with `fixed`, `sliding`,
  `allow`, and `deny` also selectable — the one-line swap Day 1 promised,
  proven end-to-end over real sockets with a real `ThreadingHTTPServer`
  (`tests/test_middleware.py::test_real_algorithm_actually_blocks_over_real_sockets`).
- 62 tests total, all green: 43 from Day 1, minus the 7 stub-contract tests
  deleted now that the stubs are real implementations, plus 20 new
  algorithm-behavior tests and 6 new/changed middleware + `build_limiter`
  tests (algorithm selection, plus the real-algorithm-over-real-sockets test).

## Requirements

Python 3.8+. No third-party packages.

## Run it

```bash
# terminal 1: boot the demo gateway with a REAL algorithm (Token Bucket by default)
python3 -m ratelimitkit.server --port 8080 --limit 3 --window 5

# terminal 2: poke it
curl -i http://127.0.0.1:8080/health
curl -i http://127.0.0.1:8080/orders

# try a different algorithm
python3 -m ratelimitkit.server --port 8080 --limit 3 --window 5 --algorithm sliding
python3 -m ratelimitkit.server --port 8080 --limit 3 --window 5 --algorithm fixed

# Day 1's reference limiters still work too (useful for isolating "is this
# a middleware bug or an algorithm bug?")
python3 -m ratelimitkit.server --port 8080 --limit 3 --window 5 --algorithm allow
python3 -m ratelimitkit.server --port 8080 --limit 3 --window 5 --deny   # legacy flag, same as --algorithm deny

# load-test it (fires N requests concurrently, tallies 200s vs 429s)
python3 -m ratelimitkit.cli --url http://127.0.0.1:8080/orders --requests 20 --concurrency 5 --clients 4
```

## Test it

```bash
python3 -m unittest discover -s tests -v
```

62 tests, all green — clock, storage, base contract, full HTTP middleware
round-trips (real sockets, a real `ThreadingHTTPServer`, including one
against a real algorithm), `build_limiter`'s algorithm selection, and the
full behavioral proof of all three algorithms.

## Project layout

```
ratelimitkit/
  clock.py       Clock / RealClock / ManualClock — swappable time      [done]
  base.py        RateLimiter ABC + RateLimitResult contract            [done]
  store.py       KeyedStore — per-key locking, no global bottleneck    [done]
  middleware.py  HTTP wiring: check() -> headers/429, ref. limiters    [done]
  server.py      Demo API gateway (stdlib http.server)                 [done — real algorithm by default]
  cli.py         Concurrent load-test tool                             [done]
  algorithms/
    fixed_window.py       FixedWindowLimiter        [done — Day 2]
    sliding_window_log.py SlidingWindowLogLimiter    [done — Day 2]
    token_bucket.py        TokenBucketLimiter        [done — Day 2]
tests/           62 passing tests
```

## Which algorithm should you actually use?

No universal answer — that's the point of building all three:

| Algorithm | Memory / key | Precision | Pick it when... |
|---|---|---|---|
| Fixed Window | O(1) | Approximate (boundary burst) | Millions of keys, loose precision is fine |
| Sliding Window Log | O(limit) | Exact | Correctness matters more than memory (payments, auth) |
| Token Bucket | O(1) | Exact rate, allows bursts | Public APIs that should tolerate occasional legitimate bursts |

## GitHub repo

Code for this project is committed locally in this repository
(`projects/2026-09-13-intermediate-ratelimitkit/`) and pending Frank's
manual push to https://github.com/fikris6889-tech/daily-teaching-series.
