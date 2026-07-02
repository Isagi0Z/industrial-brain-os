# M14 Verification Report

## Environment

| Check | Result |
|---|---|
| Docker connection | ✅ Engine 29.5.2, context `desktop-linux` |
| Running containers | 5 (postgres/redis/neo4j healthy; qdrant/minio `unhealthy` label — pre-existing `wget` healthcheck bug; both respond 200) |
| RepoWise sync | ✅ current at HEAD `f8b08df` (pre-M14) |
| Current HEAD (pre-commit) | `f8b08df` |

## Quality Gate Results

| Gate | Tool | Result |
|------|------|--------|
| Formatting | `black` | ✅ Pass (1 file reformatted during dev, then clean) |
| Lint | `ruff check .` | ✅ All checks passed (repo-wide) |
| Type check | `mypy app/` | ✅ **10 errors in 8 files — identical to the pre-M14 baseline**; 0 new. The lone hit in a touched file (`chat_use_case.py:128`) is the pre-existing `generate_stream` async-iterable typing error, shifted down by added lines — same error, not new. |
| Full suite | `pytest tests/` | ✅ **325 passed** (312 pre-M14 baseline + 13 new M14 tests), 0 failed, 0 errors |
| Docker services | direct checks | ✅ postgres/neo4j/redis/qdrant/minio all respond healthy |
| Backend startup | `uvicorn app.main:app` | ✅ Boots clean; `GraphRAGEngine initialized` (compressor constructed, lazy); `/api/v1/health` → healthy |
| Frontend build | `pnpm build` | ✅ Built in 7.64s, 0 errors |
| OpenAPI schema | live `/openapi.json` | ✅ `ChatResponseBody` exposes `citation_validation` + `response_quality_flag`; `CitationValidationOut` + `ValidatedSourceOut` present |
| Stage 8 live | in-process | ✅ `[source_1]` validated + `[source_7]` hallucinated → `validated=1, hallucinated=1, CITATION_WARNING`; bbox coords resolved; hallucinated marker stripped from answer |

## New Tests (test_pipeline_m14.py — 13 tests)

| Class | Tests | Covers |
|-------|------:|--------|
| `TestLLMLinguaCompressor` | 4 | small-context skip (no model load); passthrough when backend unavailable; parses llmlingua output into `CompressionResult`; compression failure → passthrough |
| `TestCitationValidation` | 4 | all-valid; hallucinated stripped + `CITATION_WARNING`; no markers → empty report; duplicate `[source_1]` counts once |
| `TestGraphRAGStage7` | 3 | no compressor → uncompressed result; mock compressor produces numbered context (`[source_1]`/`[source_2]` present); `_assemble_numbered_context` format |
| `TestChatStage8Integration` | 2 | compressed context fed to LLM + `[source_1]` valid / `[source_9]` hallucinated end-to-end; clean answer → `OK` flag |

## Checklist coverage

- [x] `llmlingua` integrated as Stage 7 in `GraphRAGEngine`
- [x] Compression ratio logged per request (`{original_tokens, compressed_tokens, ratio}`)
- [x] LLMLingua target ratio 0.7, configurable via env (`GRAPHRAG_COMPRESSION_RATIO`)
- [x] Compression skipped if context < 2000 tokens (`GRAPHRAG_COMPRESSION_MIN_TOKENS`)
- [x] Stage 8 parses `[source_N]`; resolves each to its chunk record (coordinates from the retrieval pipeline — see walkthrough note on the in-memory resolution vs. a redundant Postgres round-trip)
- [x] Unresolved `source_N` removed + `hallucinated_citation_count` incremented
- [x] `hallucinated_count > 0` ⇒ `response_quality_flag = "CITATION_WARNING"`
- [x] `CitationValidationReport {validated_count, hallucinated_count, quality_flag}` returned (+ `validated_sources` with absolute coords)
- [x] Compression + citation stats logged as structured JSON per request
- [x] Unit tests: LLMLingua wrapper, citation resolver, hallucinated detection

## Architecture compliance

- ADR-001 (blocking I/O off the event loop): LLMLingua compression runs in
  `run_in_threadpool`; Stage 8 resolves in-memory (no blocking DB call). ✅
- ADR-008/009 (GraphRAG / hybrid retrieval): Stage 7 operates on the
  reranked, budget-limited context — extends the pipeline, does not replace
  any stage. ✅
- Engineering Bible §1 (fail-safe / KISS): compressor degrades to passthrough
  on every failure axis. ✅
- Engineering Bible §16/§17 (structured logging / observability): per-request
  compression ratio + citation-validation stats logged. ✅
- Backward compatibility: optional compressor param + compression-aware
  fallback in `ChatUseCase` keep all 312 pre-M14 tests green. ✅

## Known environment limitation (NOT a code defect)

The LLMLingua-2 compression model is fetched from HuggingFace on first use.
This offline sandbox has no HuggingFace access (the same limitation that
leaves PaddleOCR and the `llama3.2` Ollama model unavailable), so a live
`/chat` over a large context loads the model lazily and, unable to download,
falls back to graceful passthrough (ratio 1.0). The passthrough/degradation
paths are proven by the 13 unit tests (which exercise the exception and
skip branches directly); Stage 8 was verified live end-to-end. A full
compress-with-real-model run requires an environment with model access.

## Pre-existing known issues (unchanged, NOT M14)

`worker.py` black drift; the 10 mypy baseline errors; qdrant/minio
healthcheck labels; broken dev seeder (bcrypt); frontend prettier drift;
`llama3.2` not pulled (E2E used `mistral`). None introduced or worsened by M14.
