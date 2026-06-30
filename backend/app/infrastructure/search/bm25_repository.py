"""PostgreSQL-backed BM25 keyword search repository.

Stores per-document term frequencies in `bm25_index`. At query time, applies
the BM25 ranking formula across all terms in scope.
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from typing import Callable, List

from app.domain.document.models import DocumentChunk
from app.domain.search.interfaces import IBM25Repository
from app.domain.search.models import SearchResult

logger = logging.getLogger(__name__)

_STOP_WORDS: frozenset = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "do",
        "does",
        "did",
        "not",
        "this",
        "that",
        "it",
        "its",
    }
)

_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z0-9_\-]+", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


class PostgresBM25Repository(IBM25Repository):
    def __init__(self, get_conn_fn: Callable) -> None:
        self._get_conn = get_conn_fn

    def build_index(
        self,
        document_id: str,
        chunks: List[DocumentChunk],
        role_scope: str,
    ) -> None:
        self.delete_by_document(document_id)
        if not chunks:
            return

        conn = self._get_conn()
        rows = []
        for chunk in chunks:
            tokens = _tokenize(chunk.text)
            if not tokens:
                continue
            total = len(tokens)
            freq: dict[str, int] = {}
            for t in tokens:
                freq[t] = freq.get(t, 0) + 1
            for term, count in freq.items():
                rows.append(
                    (
                        str(uuid.uuid4()),
                        document_id,
                        chunk.id,
                        chunk.chunk_index,
                        chunk.chunk_type.value,
                        term,
                        count / total,
                        role_scope,
                        "",
                        chunk.page_number,
                        chunk.parent_section_header,
                        None,
                        chunk.text,
                    )
                )

        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO bm25_index
                    (id, document_id, chunk_id, chunk_index, chunk_type, term,
                     tf, role_scope, document_title, page_number,
                     parent_section_header, bbox_json, chunk_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                rows,
            )
        conn.commit()
        logger.info(
            "BM25 index built for document %s (%d chunks)", document_id, len(chunks)
        )

    def update_document_title(self, document_id: str, title: str) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bm25_index SET document_title=%s WHERE document_id=%s",
                (title, document_id),
            )
        conn.commit()

    def search(
        self,
        query: str,
        role_scope: str,
        limit: int,
    ) -> List[SearchResult]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT document_id)
                FROM bm25_index
                WHERE role_scope = %s
                """,
                (role_scope,),
            )
            row = cur.fetchone()
            total_docs = row[0] if row else 0

        if total_docs == 0:
            return []

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT term, COUNT(DISTINCT document_id) AS df
                FROM bm25_index
                WHERE role_scope = %s AND term = ANY(%s)
                GROUP BY term
                """,
                (role_scope, list(query_terms)),
            )
            df_map = {r[0]: r[1] for r in cur.fetchall()}

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk_id, chunk_index, chunk_type, term, tf,
                       document_id, document_title, page_number,
                       parent_section_header, bbox_json, chunk_text
                FROM bm25_index
                WHERE role_scope = %s AND term = ANY(%s)
                """,
                (role_scope, list(query_terms)),
            )
            rows = cur.fetchall()

        scores: dict[str, float] = {}
        meta: dict[str, dict] = {}
        for row in rows:
            cid, ci, ctype, term, tf, did, dtitle, pnum, psh, bbox, ctext = row
            df = df_map.get(term, 1)
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1)
            score = idf * (tf * (_K1 + 1)) / (tf + _K1)
            scores[cid] = scores.get(cid, 0.0) + score
            if cid not in meta:
                meta[cid] = {
                    "chunk_index": ci,
                    "chunk_type": ctype,
                    "document_id": did,
                    "document_title": dtitle or "",
                    "page_number": pnum,
                    "parent_section_header": psh,
                    "bbox_json": bbox,
                    "chunk_text": ctext,
                }

        if not scores:
            return []

        max_score = max(scores.values()) or 1.0
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        from app.domain.document.constants import ChunkType

        results: List[SearchResult] = []
        for cid, raw_score in ranked:
            m = meta[cid]
            results.append(
                SearchResult(
                    chunk_id=cid,
                    document_id=m["document_id"],
                    document_title=m["document_title"],
                    chunk_type=ChunkType(m["chunk_type"]),
                    text=m["chunk_text"],
                    page_number=m["page_number"],
                    parent_section_header=m["parent_section_header"],
                    bbox_json=m["bbox_json"],
                    score=raw_score / max_score,
                    role_scope=role_scope,
                )
            )
        return results

    def delete_by_document(self, document_id: str) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bm25_index WHERE document_id = %s", (document_id,))
        conn.commit()
