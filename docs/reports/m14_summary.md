# M14 Summary — Full 8-Stage Pipeline (Stages 7–8)

**Milestone**: M14
**Status**: ✅ Complete
**Date**: 2026-07-02

## Delivered

Completed the 8-stage hybrid retrieval pipeline by adding Stage 7 (LLMLingua
context compression) and Stage 8 (citation validation with absolute source
coordinates), enhancing the existing `POST /api/v1/chat` flow in place — no
new endpoint, no migration.

### Stage 7 — Context Compression
- `IContextCompressor` domain port; `LLMLinguaCompressor` infra adapter with
  lazy model load and graceful passthrough on unavailable-backend /
  small-context / runtime-error.
- Wired into `GraphRAGEngine` as an optional dependency: assembles a
  source-numbered context from the reranked chunks and compresses it
  (`run_in_threadpool`, ADR-001), returning `compressed_context` +
  `CompressionResult{original_tokens, compressed_tokens, ratio, was_compressed}`
  on `HybridSearchResult`.
- Target ratio 0.7, min-token skip 2000, model — all configurable via env.

### Stage 8 — Citation Validation
- `validate_citations(answer, ordered_citations)` — pure logic: parses
  `[source_N]`, resolves valid markers to `ValidatedSource` records with
  absolute `document_id/page_number/bbox_json`, strips hallucinated markers,
  and returns a `CitationValidationReport{validated_count, hallucinated_count,
  quality_flag, validated_sources}`.
- Wired into `ChatUseCase.chat` + `finalize`; the cleaned answer + report +
  `response_quality_flag` are returned on every `/chat` response (HTTP and WS).

## Files created

```
backend/app/infrastructure/graphrag/llmlingua_compressor.py
backend/app/application/chat/citation_validation.py
backend/tests/test_pipeline_m14.py
docs/walkthroughs/m14_walkthrough.md
docs/verification/m14_verification.md
docs/reports/m14_summary.md
```

## Files modified

```
backend/app/domain/graphrag/models.py          — CompressionResult; HybridSearchResult.{compressed_context,compression}
backend/app/domain/graphrag/interfaces.py       — IContextCompressor
backend/app/domain/chat/models.py               — ValidatedSource, CitationValidationReport, Citation.bbox_json, ChatResponse.{citation_validation,response_quality_flag}
backend/app/application/graphrag/graphrag_engine.py  — Stage 7 wiring + _assemble_numbered_context
backend/app/application/chat/chat_use_case.py    — Stage 8 wiring + compressed-context path + _citations_from_ranked
backend/app/infrastructure/graphrag/redis_graphrag_cache.py  — serialize/deserialize compression fields
backend/app/infrastructure/config/settings.py    — GRAPHRAG_COMPRESSION_* + LLMLINGUA_MODEL
backend/app/infrastructure/di/container.py        — get_context_compressor wired into get_graphrag_engine
backend/app/presentation/api/v1/endpoints/chat.py — CitationValidationOut/ValidatedSourceOut + response wiring (HTTP + WS)
backend/ai/prompts/knowledge_copilot.yaml         — instruct [source_N] citation over numbered context
backend/requirements.txt                          — +llmlingua>=0.2.2
docs/implementation_roadmap.md                    — M14 checklist [x] + SHA
```

## Key technical decisions

- **Optional compressor + compression-aware fallback.** `GraphRAGEngine`
  takes `compressor=None` by default and `ChatUseCase.prepare` uses the
  compressed, source-numbered context only when Stage 7 ran, else the
  original `ContextBuilder` path — so all 312 pre-M14 tests stay green and
  the endpoint degrades cleanly when compression is disabled/unavailable.
- **Source numbering lives with Stage 7 assembly**, making `[source_N]` the
  single contract shared by the compressed prompt and Stage 8 resolution.
- **In-memory citation resolution** rather than a redundant Postgres
  round-trip: retrieved chunks already carry their DB coordinates, so Stage 8
  stays off the blocking path (ADR-001) while still returning the same
  absolute coordinates.
- **Graceful degradation everywhere** — LLMLingua is lazy-loaded and every
  failure axis (missing lib, un-downloadable model, small context, runtime
  error) falls back to a labelled passthrough, matching the project's
  established offline-degradation pattern (PaddleOCR / embeddings).

## Blockers encountered

- **PyPI SSL failure** installing `llmlingua` in the sandbox — resolved with
  `--trusted-host` (the environment's known cert issue, same root cause as
  the embedding service's SSL workaround).
- **LLMLingua-2 model download unavailable offline** — handled by design via
  graceful passthrough; the compression logic (parse/skip/fail paths) is
  proven by unit tests rather than a live model run.

## Test results

- **13 new M14 tests** (`test_pipeline_m14.py`) — all pass.
- **325 total backend tests pass** (312 baseline + 13), 0 failed.
- Live: OpenAPI exposes the new fields; Stage 8 verified end-to-end
  (validated + hallucinated + `CITATION_WARNING` + bbox coords + marker
  stripped); backend boots; frontend builds.

## What M14 unlocks

The retrieval pipeline is now the full 8 stages end-to-end. The remaining
Phase-3 items are M15 (event-driven async ingestion, ADR-015) and M16
(evaluation layer — which consumes the `CitationValidationReport` /
hallucination signal M14 now produces), followed by the Final Demo phase.
