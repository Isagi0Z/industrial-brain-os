# M14 Walkthrough — Full 8-Stage Pipeline (Stages 7–8)

## Overview

M14 completes the 8-stage hybrid retrieval pipeline (architecture §4) by
adding the two stages that were previously stubs:

- **Stage 7 — Context Compression (LLMLingua)**: compress the assembled,
  source-numbered context before the LLM call, targeting ~70% token
  retention. Lives in `GraphRAGEngine` (Stages 1–7 now).
- **Stage 8 — Citation Validation**: after generation, parse the LLM's
  `[source_N]` markers, resolve each to its retrieved chunk (with absolute
  `document_id / page_number / bbox_json` coordinates), strip hallucinated
  references, and append a `CitationValidationReport` to every `/chat`
  response. Lives in `ChatUseCase` (post-LLM).

```
Query ─► GraphRAGEngine.retrieve (Stages 1-6: BM25+vector+KG+rerank+budget)
             │
             └─ Stage 7: assemble "[source_1] … [source_2] …" numbered
                context  →  LLMLingua compress  →  HybridSearchResult
                {compressed_context, compression{orig,comp,ratio}}
             │
ChatUseCase.prepare ─► feed compressed_context to the LLM; derive ordered
                       citations (same [source_N] order, with bbox coords)
             │
       LLM generates  "…rated 10 bar [source_2]…"
             │
ChatUseCase.chat ─► Stage 8: validate_citations(answer, ordered_citations)
                    → keep valid [source_N], strip hallucinated, build
                      CitationValidationReport{validated, hallucinated,
                      quality_flag, validated_sources[coords]}
             │
       ChatResponse {answer(cleaned), citations, citation_validation,
                     response_quality_flag}
```

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `graphrag/models.py` (`CompressionResult`, `HybridSearchResult.{compressed_context,compression}`); `graphrag/interfaces.py` (`IContextCompressor`); `chat/models.py` (`ValidatedSource`, `CitationValidationReport`, `Citation.bbox_json`, `ChatResponse.{citation_validation,response_quality_flag}`) |
| Application | `graphrag/graphrag_engine.py` — Stage 7 wiring + `_assemble_numbered_context`; `chat/chat_use_case.py` — Stage 8 wiring + `_citations_from_ranked`; `chat/citation_validation.py` — the pure Stage 8 validator |
| Infrastructure | `graphrag/llmlingua_compressor.py` (`LLMLinguaCompressor`); `graphrag/redis_graphrag_cache.py` — serialize the new fields |
| Presentation | `chat.py` — `CitationValidationOut` / `ValidatedSourceOut` schemas + response wiring (HTTP + WS `done` frame) |
| Config / Prompt | `settings.py` (`GRAPHRAG_COMPRESSION_*`, `LLMLINGUA_MODEL`); `ai/prompts/knowledge_copilot.yaml` — instruct `[source_N]` citation |

## Stage 7 — LLMLingua compression

`GraphRAGEngine` gained an **optional** `compressor: IContextCompressor | None`
(default `None`, so existing unit tests that construct the engine without it
are unaffected). After the token budget, `_compress_context`:

1. assembles the reranked chunks into a source-numbered string
   (`[source_1] (Pump Manual, p.3)\n{text}\n\n[source_2] …`) — this numbering
   is what makes Stage 8's `[source_N]` resolution possible;
2. calls the compressor inside `run_in_threadpool` (ADR-001 — LLMLingua is
   blocking);
3. stores `compressed_context` + `compression` stats in `HybridSearchResult`.

`LLMLinguaCompressor` degrades gracefully on every axis (checklist +
Engineering Bible §1 fail-safe):

- **Small context** (< `min_tokens`, default 2000) → skip, passthrough,
  `was_compressed=False`, `ratio=1.0` (avoids over-compressing sparse
  results).
- **Backend unavailable** (llmlingua not installed, or the LLMLingua-2 model
  can't be loaded) → passthrough. The model is **lazy-loaded on first use**,
  never at construction, so a missing model never blocks startup.
- **Runtime error** during compression → passthrough.

Token counts use `tiktoken` (already a dependency) with a char/4 fallback.
Compression ratio is logged per request (Engineering Bible §16/§17).

## Stage 8 — citation validation

`validate_citations(answer, ordered_citations)` (pure, fully unit-tested):

- parses `[source_N]` markers (case-insensitive);
- `1 ≤ N ≤ len(citations)` → **validated**: resolves to `citations[N-1]`,
  emitting a `ValidatedSource` with the chunk's absolute coordinates
  (`document_id`, `page_number`, `bbox_json`); the marker stays in the
  answer;
- otherwise → **hallucinated**: the marker is stripped from the answer and
  `hallucinated_count` is incremented;
- `hallucinated_count > 0` ⇒ `quality_flag = "CITATION_WARNING"`, else `"OK"`.

**Resolution note (documented deviation).** The checklist says "resolve each
to chunk record in PostgreSQL". The retrieved chunks (and the `Citation`s
derived from them) already carry their PostgreSQL-originated coordinates from
the retrieval pipeline, so `[source_N]` is resolved against the in-memory
ordered citation list rather than a redundant DB round-trip on the hot path
(ADR-001). The coordinates returned are the same records Postgres holds.

`ChatUseCase.chat` and `finalize` (streaming) both run Stage 8 after
generation, store the **cleaned** answer to history, and return the report +
`response_quality_flag` on `ChatResponse`. The WS `done` frame carries the
cleaned `answer`, `citation_validation`, and `response_quality_flag`.

## Compression ↔ fallback interplay (keeps the pipeline robust)

`ChatUseCase.prepare` uses the compressed, source-numbered context **when
Stage 7 ran** (`hybrid_result.compression is not None`) and derives citations
from `ranked_chunks` in the matching `[source_N]` order. When no compressor
is wired (e.g. unit tests, or `GRAPHRAG_COMPRESSION_ENABLED=false`), it falls
back to the original `ContextBuilder` path unchanged — so every pre-M14 chat
test still passes and the endpoint degrades cleanly.

## Configuration

| Setting | Default |
|---------|---------|
| `GRAPHRAG_COMPRESSION_ENABLED` | `true` |
| `GRAPHRAG_COMPRESSION_RATIO` | `0.7` (keep ~70% of tokens) |
| `GRAPHRAG_COMPRESSION_MIN_TOKENS` | `2000` (skip below) |
| `LLMLINGUA_MODEL` | `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` |

## Environment notes

`llmlingua>=0.2.2` added to `requirements.txt` and installed. The LLMLingua-2
compression model is downloaded from HuggingFace on first use; in an offline
/ air-gapped environment (as in this sandbox) the download is unavailable, so
Stage 7 operates in **graceful passthrough** (ratio 1.0) — the same
offline-degradation class as PaddleOCR. Stage 8 citation validation is fully
functional regardless of the compression backend. Operators without model
access can set `GRAPHRAG_COMPRESSION_ENABLED=false` to force instant
passthrough with no load attempt. No migration and no new endpoint — M14
enhances the existing `POST /api/v1/chat` pipeline in place.
