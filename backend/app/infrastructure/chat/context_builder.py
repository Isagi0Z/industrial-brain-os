from __future__ import annotations

import logging
from typing import List, Tuple

from app.domain.chat.interfaces import IContextBuilder
from app.domain.chat.models import Citation
from app.domain.search.models import SearchResult

logger = logging.getLogger(__name__)

_APPROX_CHARS_PER_TOKEN = 4


class ContextBuilder(IContextBuilder):
    def build(
        self,
        results: List[SearchResult],
        max_context_tokens: int,
    ) -> Tuple[str, List[Citation]]:
        seen_chunk_ids: set[str] = set()
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)

        blocks: List[str] = []
        citations: List[Citation] = []
        token_budget = max_context_tokens

        for result in sorted_results:
            if result.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(result.chunk_id)

            page_str = f"p.{result.page_number}" if result.page_number else "p.?"
            block = f"[Source: {result.document_title}, {page_str}]\n{result.text}"
            approx_tokens = len(block) // _APPROX_CHARS_PER_TOKEN
            if approx_tokens > token_budget:
                break

            blocks.append(block)
            token_budget -= approx_tokens
            citations.append(
                Citation(
                    chunk_id=result.chunk_id,
                    document_title=result.document_title,
                    page_number=result.page_number,
                    chunk_text_excerpt=result.text[:200],
                    score=round(result.score, 4),
                    storage_key=result.document_id,
                )
            )

        context_text = "\n\n---\n\n".join(blocks)
        logger.debug(
            "Context built",
            extra={
                "chunks_used": len(blocks),
                "approx_tokens_used": max_context_tokens - token_budget,
            },
        )
        return context_text, citations
