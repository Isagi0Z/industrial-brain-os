"""Latency benchmark (M20, NFR-03) — `make benchmark`.

Drives the running API and reports p50/p95/p99 latency for two paths:

  * ``GET /api/v1/search/semantic`` — target p50 < 500 ms
  * ``POST /api/v1/chat``           — full GraphRAG pipeline, target p50 < 3000 ms

Exits non-zero if either p50 target is exceeded. Auth via a token minted from
the app's token service (no password needed) so the benchmark is self-contained.

Usage:
    python scripts/benchmark_latency.py [--base URL] [--search-n 50] [--chat-n 20]
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import List

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

_SEARCH_P50_MS = 500.0
_CHAT_P50_MS = 3000.0

_QUERIES = [
    "rated discharge pressure of pump P-102A",
    "how to isolate pump P-102A",
    "bearing seizure failure mode",
    "flow transmitter FT-101 range",
    "lockout tagout cooling loop A",
]


def _mint_token() -> str:
    from app.infrastructure.di.container import container

    auth = container.get_auth_use_case()
    users = container.get_postgres().cursor()
    users.execute("SELECT id, email FROM users LIMIT 1")
    row = users.fetchone()
    if not row:
        raise SystemExit("no users in the database — cannot mint a benchmark token")
    return auth.token_service.create_access_token(data={"sub": row[0], "email": row[1]})


def _percentiles(samples: List[float]) -> dict:
    s = sorted(samples)
    q = statistics.quantiles(s, n=100) if len(s) > 1 else [s[0]] * 99
    return {
        "n": len(s),
        "p50": round(statistics.median(s), 1),
        "p95": round(q[94], 1),
        "p99": round(q[98], 1),
        "min": round(s[0], 1),
        "max": round(s[-1], 1),
    }


def _bench_search(client: httpx.Client, headers: dict, n: int) -> List[float]:
    times: List[float] = []
    for i in range(n):
        q = _QUERIES[i % len(_QUERIES)]
        t0 = time.perf_counter()
        r = client.get(
            "/api/v1/search/semantic", params={"q": q, "limit": 10}, headers=headers
        )
        r.raise_for_status()
        times.append((time.perf_counter() - t0) * 1000)
    return times


def _bench_chat(client: httpx.Client, headers: dict, n: int) -> List[float]:
    times: List[float] = []
    for i in range(n):
        q = _QUERIES[i % len(_QUERIES)]
        body = {
            "query": q,
            "session_id": f"bench-{i}",
            "top_k": 5,
            "role_scope": "public",
        }
        t0 = time.perf_counter()
        r = client.post("/api/v1/chat", json=body, headers=headers)
        r.raise_for_status()
        times.append((time.perf_counter() - t0) * 1000)
    return times


def main() -> int:
    parser = argparse.ArgumentParser(description="API latency benchmark (NFR-03).")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--search-n", type=int, default=50)
    parser.add_argument("--chat-n", type=int, default=20)
    parser.add_argument("--skip-chat", action="store_true", help="search only")
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {_mint_token()}"}
    failed = False
    with httpx.Client(base_url=args.base, timeout=120.0) as client:
        print(f"Semantic search — {args.search_n} requests:")
        s = _percentiles(_bench_search(client, headers, args.search_n))
        print(f"  {s}")
        print(
            f"  {'PASS' if s['p50'] < _SEARCH_P50_MS else 'FAIL'}: "
            f"p50 {s['p50']}ms vs target {_SEARCH_P50_MS}ms"
        )
        failed |= s["p50"] >= _SEARCH_P50_MS

        if not args.skip_chat:
            print(f"Chat (GraphRAG) — {args.chat_n} requests:")
            c = _percentiles(_bench_chat(client, headers, args.chat_n))
            print(f"  {c}")
            print(
                f"  {'PASS' if c['p50'] < _CHAT_P50_MS else 'FAIL'}: "
                f"p50 {c['p50']}ms vs target {_CHAT_P50_MS}ms"
            )
            failed |= c["p50"] >= _CHAT_P50_MS

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
