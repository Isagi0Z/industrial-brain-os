"""Pipeline latency benchmark (Performance & Ingestion Upgrade, Parts 2/4/6).

Measures per-stage latency so optimizations are backed by numbers, not guesses:
  - query embedding (bge-large, cached singleton)
  - cross-encoder rerank at growing candidate counts (corpus-growth cost)
  - Ollama generation: WARM (keep_alive pinned + warmed) vs COLD (after an idle
    unload), which quantifies the model-reload penalty that keep_alive removes

Run:  python scripts/benchmark_pipeline.py
Writes docs/performance/benchmark_results.json and prints a summary table.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("USE_TF", "0")

# ~1.1k-token representative retrieved context.
_CONTEXT = (
    "Centrifugal Pump P-102A is part of Refining Unit 03. Rated discharge "
    "pressure is 12 bar and rated flow is 320 m3/h. It is monitored by flow "
    "transmitter FT-101 and thermocouple TE-202 (bearing temperature). Known "
    "failure modes include bearing seizure (FM-BRG-01, HIGH severity) and "
    "mechanical seal gasket leakage. Before maintenance, isolate the pump: close "
    "the suction and discharge valves, apply lockout-tagout, and depressurise the "
    "casing. Work order WO-99201 references a bearing seizure repair. "
) * 8


def _stats(samples):
    return {
        "runs": len(samples),
        "median_ms": round(statistics.median(samples), 1),
        "min_ms": round(min(samples), 1),
        "max_ms": round(max(samples), 1),
    }


def bench_embedding():
    try:
        from app.infrastructure.search.embedding_service import (
            SentenceTransformerEmbedder,
            _EMBEDDING_AVAILABLE,
        )
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    if not _EMBEDDING_AVAILABLE:
        return {"available": False, "reason": "sentence-transformers/model offline"}
    emb = SentenceTransformerEmbedder()
    q = "What is the rated discharge pressure of pump P-102A?"
    emb.embed_one(q)  # warm
    samples = []
    for _ in range(5):
        t0 = time.monotonic()
        emb.embed_one(q)
        samples.append((time.monotonic() - t0) * 1000)
    return {"available": True, **_stats(samples)}


def bench_rerank():
    try:
        from app.infrastructure.graphrag import cross_encoder_reranker as cre
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    if not cre._RERANKER_AVAILABLE:
        return {"available": False, "reason": "cross-encoder/model offline"}
    try:
        model = cre._get_model("BAAI/bge-reranker-large")
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": str(exc)}
    q = "rated discharge pressure of pump P-102A"
    doc = "Pump P-102A rated discharge pressure is 12 bar; rated flow 320 m3/h. " * 6
    model.predict([(q, doc), (q, doc)])  # warm
    by_count = {}
    for n in (5, 10, 20, 40):
        samples = []
        for _ in range(3):
            t0 = time.monotonic()
            model.predict([(q, doc)] * n)
            samples.append((time.monotonic() - t0) * 1000)
        by_count[str(n)] = _stats(samples)
    return {"available": True, "by_candidate_count": by_count}


async def bench_ollama():
    from app.infrastructure.chat.ollama_gateway import OllamaGateway
    from app.infrastructure.config.settings import settings

    msgs = [
        {"role": "system", "content": "Answer using the context and cite sources."},
        {"role": "user", "content": _CONTEXT + "\n\nQ: rated discharge pressure of P-102A?"},
    ]
    result = {"keep_alive_setting": settings.OLLAMA_KEEP_ALIVE, "num_ctx": settings.OLLAMA_NUM_CTX}

    # WARM: keep_alive pinned + pre-warmed
    warm = OllamaGateway(
        settings.OLLAMA_HOST, settings.OLLAMA_PORT, settings.OLLAMA_MODEL,
        keep_alive="-1", num_ctx=settings.OLLAMA_NUM_CTX,
    )
    if not (await warm.health()).get("available"):
        return {"available": False, "reason": "ollama not reachable"}
    await warm.warm_up()

    totals = []
    last_pt = last_ct = 0
    for _ in range(2):
        t0 = time.monotonic()
        _txt, pt, ct = await warm.generate(msgs, 128)
        totals.append((time.monotonic() - t0) * 1000)
        last_pt, last_ct = pt, ct
    result["warm_generate"] = {**_stats(totals), "prompt_tokens": last_pt, "completion_tokens": last_ct}

    # WARM first-token (streaming)
    t0 = time.monotonic()
    first_ms = None
    n_tok = 0
    async for _tok in warm.generate_stream(msgs, 128):
        n_tok += 1
        if first_ms is None:
            first_ms = round((time.monotonic() - t0) * 1000, 1)
    result["warm_first_token_ms"] = first_ms
    result["warm_stream_total_ms"] = round((time.monotonic() - t0) * 1000, 1)

    # COLD: keep_alive=0 unloads after the ping; the next call pays the reload.
    cold = OllamaGateway(
        settings.OLLAMA_HOST, settings.OLLAMA_PORT, settings.OLLAMA_MODEL, keep_alive=0,
    )
    await cold.generate([{"role": "user", "content": "hi"}], 1)  # unloads after
    await asyncio.sleep(4)
    t0 = time.monotonic()
    await cold.generate(msgs, 128)
    result["cold_generate_ms_includes_reload"] = round((time.monotonic() - t0) * 1000, 1)

    warm_med = result["warm_generate"]["median_ms"]
    result["reload_penalty_ms_saved_by_keep_alive"] = round(
        result["cold_generate_ms_includes_reload"] - warm_med, 1
    )
    await warm.aclose()
    await cold.aclose()
    result["available"] = True
    return result


def main() -> int:
    print("Benchmarking pipeline stages (this loads models and runs CPU inference)…\n")
    out = {
        "embedding": bench_embedding(),
        "rerank": bench_rerank(),
        "ollama": asyncio.run(bench_ollama()),
    }
    print("== Embedding (query) ==")
    print(f"  {out['embedding']}")
    print("== Rerank (cross-encoder) ==")
    print(f"  {out['rerank']}")
    print("== Ollama generation ==")
    for k, v in out["ollama"].items():
        print(f"  {k}: {v}")

    dest = ROOT / "docs" / "performance" / "benchmark_results.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
