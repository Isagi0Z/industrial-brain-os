"""Knowledge Brain domain models (M9 — LangGraph agent state machine).

AgentState is the single state object threaded through every LangGraph node.
It holds only domain types — no framework (LangGraph, FastAPI) types leak in.
"""

from __future__ import annotations

from typing import List, TypedDict

from app.domain.chat.models import Citation
from app.domain.graphrag.models import KGPath
from app.domain.search.models import SearchResult


class AgentState(TypedDict):
    query: str
    session_id: str
    user_role: str
    retrieved_chunks: List[SearchResult]
    kg_paths: List[KGPath]
    draft_answer: str
    citations: List[Citation]
    step_count: int
    error_flag: bool
