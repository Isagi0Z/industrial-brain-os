# M8 Walkthrough — GraphRAG Engine (Hybrid Retrieval Pipeline, Stages 1–6)

## Overview

M8 replaces the M5 direct-vector-search lookup in `/chat` with the full
6-stage hybrid retrieval pipeline from the architecture (§4). Every chat
query now runs through `GraphRAGEngine.retrieve()`, which combines lexical
search (BM25), dense vector search (Qdrant), and knowledge-graph traversal
(Neo4j) into a single, cross-encoder-reranked, token-budgeted context.

```
ChatUseCase.prepare()
    │
    └─ GraphRAGEngine.retrieve(query, role_scope, top_k)
            │
            ├─ Redis cache lookup (hash(query + role_scope), 5-min TTL)
            │      │ hit → return cached HybridSearchResult
            │      │ miss ↓
            │
            ├─ asyncio.gather(                       ← Stages 1-4 concurrent
            │      Stage 1+2: EmbeddingUseCase.search_keyword()   (BM25 + role_scope filter)
            │      Stage 3+2: EmbeddingUseCase.search_semantic()  (Qdrant + role_scope filter)
            │      Stage 4:   Neo4jKGTraversalService.traverse()  (APOC subgraphAll, depth ≤ 2)
            │  )
            │
            ├─ Stage 5: _merge_candidates()           ← dedupe by chunk_id, keep max score
            │
            ├─ Stage 6: CrossEncoderReranker.rerank()  ← bge-reranker-large, in threadpool
            │
            ├─ _apply_token_budget()                  ← discard beyond 6000 tokens
            │
            └─ Redis cache.set() → HybridSearchResult
```

## Clean Architecture Layer Map

| Layer | Files |
|-------|-------|
| Domain | `domain/graphrag/models.py`, `domain/graphrag/interfaces.py` |
| Application | `application/graphrag/graphrag_engine.py` |
| Infrastructure | `infrastructure/graphrag/neo4j_kg_traversal.py`, `cross_encoder_reranker.py`, `redis_graphrag_cache.py` |

`GraphRAGEngine` depends only on domain interfaces (`IEntityExtractor` from
M7, `IKGTraversalService`, `ICrossEncoderReranker`, `IGraphRAGCache`) plus
the existing `EmbeddingUseCase` (M4) for Stages 1–3 — no concrete
infrastructure types leak into the application layer (ADR-013).

## Stage-by-Stage Detail

### Stages 1–3: Lexical + Metadata Filter + Dense Vector

Reuses `EmbeddingUseCase.search_keyword()` (BM25, PostgreSQL) and
`search_semantic()` (Qdrant) from M4 unchanged. Both already accept
`role_scope` and apply it as a hard filter at the query level — this
satisfies Stage 2 (Metadata Filtering / RBAC) without a separate filtering
pass, since filtering *before* the vector/lexical search is cheaper and
more correct than filtering candidates after the fact.

### Stage 4: KG Traversal

`GraphRAGEngine._extract_query_entities()` wraps the raw query string in a
throwaway `DocumentChunk` and runs it through the M7 `SpacyEntityExtractor`
— the exact same entity-tag recognizer used during document ingestion, so
a query mentioning `"P-102A"` is tagged identically to how it would be
tagged inside a document chunk.

Recognized tags are passed to `Neo4jKGTraversalService.traverse()`, which
runs one Cypher query per tag:

```cypher
MATCH (n {tag_number: $tag})
CALL apoc.path.subgraphAll(n, {maxLevel: $max_level, limit: $limit})
YIELD relationships
UNWIND relationships AS rel
RETURN startNode(rel).tag_number AS source_tag,
       labels(startNode(rel))[0] AS source_type,
       type(rel) AS relation_type,
       endNode(rel).tag_number AS target_tag,
       labels(endNode(rel))[0] AS target_type
```

`maxLevel` is hardcoded to 2 (ADR-004 mitigation — Neo4j Community is
single-node, so unbounded traversal on a large graph is a real performance
risk). A failure on any single tag is caught and logged; it does not abort
traversal for the remaining tags (mirrors the per-chunk isolation pattern
from M7's `ExtractionUseCase`).

### Stage 5: GraphRAG Synthesis

`_merge_candidates()` deduplicates the combined BM25 + vector result sets
by `chunk_id`, keeping the higher-scoring instance of any chunk retrieved
by both paths. KG paths are rendered as a Markdown table via
`HybridSearchResult.kg_paths_as_markdown()`:

```
| Source | Relation | Target |
| --- | --- | --- |
| Sensor:FT-101 | MONITORS | Equipment:P-102A |
```

`ChatUseCase.prepare()` appends this table under a
`### Related Knowledge Graph Relationships` heading in the LLM context —
raw subgraphs are never passed to the LLM directly (Engineering Bible §20).

### Stage 6: Cross-Encoder Reranking

`CrossEncoderReranker` loads `BAAI/bge-reranker-large` lazily on first use,
mirroring the exact pattern `SentenceTransformerEmbedder` (M4) already
established for the embedding model. Inference runs via
`starlette.concurrency.run_in_threadpool` so the event loop is never
blocked. If the model can't be loaded (no network, no local cache), the
reranker degrades to passing candidates through in their original
retrieval-score order rather than failing the whole pipeline.

### Token Budget

`_apply_token_budget()` walks the reranked list (already sorted descending)
and stops as soon as a chunk would exceed the remaining budget
(`GRAPHRAG_TOKEN_BUDGET`, default 6000 tokens, ~4 chars/token
approximation) — consistent with how `ContextBuilder` already truncates in
M5.

### Caching

`RedisGraphRAGCache` serializes the full `HybridSearchResult` (ranked
chunks, KG paths, entity mentions) to JSON, keyed by
`sha256(query + role_scope)`, with a 5-minute TTL
(`GRAPHRAG_CACHE_TTL_SECONDS`). A cache hit skips the entire retrieval
pipeline — verified live: a second identical query returns the exact same
`HybridSearchResult` object with zero additional Neo4j/Qdrant/Postgres
calls.

## Configuration

| Setting | Default |
|---------|---------|
| `GRAPHRAG_RERANKER_MODEL` | `BAAI/bge-reranker-large` |
| `GRAPHRAG_CACHE_TTL_SECONDS` | `300` |
| `GRAPHRAG_TOKEN_BUDGET` | `6000` |
| `GRAPHRAG_MAX_KG_DEPTH` | `2` |
| `GRAPHRAG_KG_TRAVERSAL_LIMIT` | `50` |

## `/chat` Integration

`ChatUseCase` no longer depends on `EmbeddingUseCase` directly — its
constructor now takes an `IGraphRAGEngine`. `prepare()` calls
`graphrag.retrieve()`, extracts the underlying `SearchResult`s from
`ranked_chunks` for the existing `ContextBuilder`, and appends the KG
Markdown table if any paths were found. The `/api/v1/chat` REST and
WebSocket endpoints required no changes — the swap is fully transparent to
the presentation layer.

## DI Wiring

`DIContainer` gained:
- `get_entity_extractor()` — singleton `SpacyEntityExtractor`, now shared
  between `ExtractionUseCase` (M7) and `GraphRAGEngine` (M8) instead of
  loading the spaCy model twice.
- `get_kg_traversal_service()`, `get_cross_encoder_reranker()`,
  `get_graphrag_cache()`, `get_graphrag_engine()`
- `_build_primary_gateway()` / `_build_fallback_gateway()` — extracted from
  `get_chat_use_case()` so `get_extraction_use_case()` (M7) no longer reaches
  into `ChatUseCase`'s private `_primary` attribute to get an `IModelGateway`.

## Environment Notes

This session's dev venv was missing several M7 hard dependencies
(`spacy`, `rapidfuzz`) plus base-platform deps (`PyJWT`, `passlib[bcrypt]`)
that are imported unconditionally by `container.py` — meaning the DI
container (and therefore any integration test) could not even be imported
before these were installed. `spacy`/`rapidfuzz` have been added to
`requirements.txt`, closing a gap from the M7 session. `qdrant-client` had
also drifted to an incompatible 1.16.x install; it was pinned back to the
`requirements.txt`-specified `<1.10.0` range.
