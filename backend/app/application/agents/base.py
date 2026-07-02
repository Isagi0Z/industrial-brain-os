"""Shared LangGraph sub-brain agent primitives.

Extracted (architecture-refactor phase) from the five per-brain agents
(knowledge/maintenance/compliance/rca/lessons), which had been built as
near-identical copies. Every helper here reproduces the exact logic that
was previously duplicated — this module is behaviour-preserving by
construction, not a redesign:

- ``StepLimitExceededError`` — the identical exception all five raised.
- ``load_prompt`` — the identical YAML prompt loader (was ``_load_prompt``).
- ``error_router`` — the identical conditional-edge selector (was
  ``_error_or``): returns ``"error"`` when ``error_flag`` is set, else the
  given default.
- ``format_context_blocks`` — the identical chunk→markdown formatter used by
  the knowledge/maintenance/compliance synthesis nodes.
- ``validate_chunk_citations`` — the identical ``[[chunk:<id>]]`` →
  ``Citation`` validator used by those same three ``format_response`` nodes
  (drops hallucinated/duplicate chunk ids).
- ``render_citations`` — the identical footnote-substitution + Sources block
  renderer; the only per-brain variation (the Sources heading text) is a
  parameter so behaviour is unchanged.
- ``BaseBrainAgent`` — the shared step-limit guard, error-router edge
  selector, and (for the chat-style brains) chat-history persistence.
  Subclasses still own their own ``__init__``, graph construction, and
  nodes. The one per-brain difference in the step-limit log message (chat
  brains key on ``session_id``; the lessons ingestion graph keys on
  ``asset_tag``) is preserved via the overridable ``_step_limit_context``
  hook, so the emitted messages are byte-identical to before.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, List, Mapping

import yaml  # type: ignore[import-untyped]

from app.domain.chat.interfaces import IChatHistoryRepository
from app.domain.chat.models import ChatMessage, Citation, MessageRole
from app.domain.search.models import SearchResult

# The inline source-citation marker convention shared by every brain that
# emits chunk citations: ``[[chunk:<chunk_id>]]``.
CITATION_PATTERN = re.compile(r"\[\[chunk:([^\]]+)\]\]")


class StepLimitExceededError(Exception):
    """Raised when an agent exceeds its configured max step count."""


def load_prompt(path: Path) -> dict:
    """Load a YAML prompt file into a dict (empty dict on empty file)."""
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def error_router(default: str) -> Callable[[Mapping[str, Any]], str]:
    """Return a LangGraph conditional-edge selector that routes to ``"error"``
    when the state's ``error_flag`` is set, otherwise to ``default``."""

    def _selector(state: Mapping[str, Any]) -> str:
        return "error" if state["error_flag"] else default

    return _selector


def format_context_blocks(chunks: List[SearchResult]) -> str:
    """Format retrieved chunks into the cit/id-tagged markdown blocks fed to
    the synthesis prompt (deduplicated/ranked upstream by GraphRAG)."""
    blocks = []
    for c in chunks:
        page_str = f"p.{c.page_number}" if c.page_number else "p.?"
        blocks.append(
            f"[chunk_id: {c.chunk_id} | {c.document_title}, {page_str}]\n{c.text}"
        )
    return "\n\n---\n\n".join(blocks)


def validate_chunk_citations(
    text: str, retrieved_chunks: List[SearchResult]
) -> List[Citation]:
    """Resolve every ``[[chunk:<id>]]`` marker in ``text`` to a ``Citation``,
    keeping only markers that reference a real retrieved chunk id and
    dropping duplicates — hallucinated references are silently dropped."""
    by_chunk_id = {c.chunk_id: c for c in retrieved_chunks}
    seen: set = set()
    citations: List[Citation] = []
    for match in CITATION_PATTERN.finditer(text):
        chunk_id = match.group(1)
        if chunk_id in by_chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            sr = by_chunk_id[chunk_id]
            citations.append(
                Citation(
                    chunk_id=sr.chunk_id,
                    document_title=sr.document_title,
                    page_number=sr.page_number,
                    chunk_text_excerpt=sr.text[:200],
                    score=round(sr.score, 4),
                    storage_key=sr.document_id,
                )
            )
    return citations


def render_citations(
    text: str, citations: List[Citation], sources_header: str = "**Sources:**"
) -> str:
    """Replace ``[[chunk:<id>]]`` markers with numbered footnotes and append a
    Sources list. ``sources_header`` lets a brain use its own heading (e.g.
    the Maintenance brain's ``**Manual Sources:**``) with identical logic."""
    footnote_of = {c.chunk_id: i + 1 for i, c in enumerate(citations)}

    def _replace(match: "re.Match[str]") -> str:
        chunk_id = match.group(1)
        return f"[{footnote_of[chunk_id]}]" if chunk_id in footnote_of else ""

    rendered = CITATION_PATTERN.sub(_replace, text)

    if citations:
        lines = ["", sources_header]
        for i, c in enumerate(citations, start=1):
            page_str = f"p.{c.page_number}" if c.page_number else "p.?"
            lines.append(f"{i}. {c.document_title}, {page_str}")
        rendered = rendered.rstrip() + "\n" + "\n".join(lines)

    return rendered


class BaseBrainAgent:
    """Shared mechanics for the LangGraph sub-brain agents.

    Provides the step-limit guard (Engineering Bible §21), the error-router
    conditional-edge selector, and — for the chat-style brains — chat-history
    persistence. Subclasses own their ``__init__``, ``_build_graph``, and
    node methods. These attributes are declared here for typing only;
    concrete subclasses assign them in their own ``__init__``.
    """

    _max_steps: int
    _history: IChatHistoryRepository
    _session_ttl: int

    def _check_step_limit(self, state: Mapping[str, Any]) -> int:
        """Return the incremented step count, raising if it would exceed the
        configured ceiling. LangGraph merges only a node's *returned* dict
        into managed state, so every node must include this value in its own
        return dict."""
        new_count = state["step_count"] + 1
        if new_count > self._max_steps:
            raise StepLimitExceededError(
                f"STEP_LIMIT_EXCEEDED: exceeded {self._max_steps} steps "
                f"({self._step_limit_context(state)})"
            )
        return new_count

    def _step_limit_context(self, state: Mapping[str, Any]) -> str:
        """Identifier embedded in the step-limit error message. Chat brains
        key on ``session_id`` (the default); brains whose state has no
        ``session_id`` override this."""
        return f"session={state['session_id']}"

    @staticmethod
    def _error_or(default: str) -> Callable[[Mapping[str, Any]], str]:
        """Instance-accessible alias for ``error_router`` — keeps the
        ``self._error_or(default=...)`` call shape used in ``_build_graph``."""
        return error_router(default)

    def _persist_turn(
        self, session_id: str, query: str, state: Mapping[str, Any]
    ) -> None:
        """Append the (user query, assistant answer) pair to Redis chat
        history. Used by the single-shot chat brains (knowledge/maintenance/
        compliance); reads the answer from ``state['draft_answer']``."""
        user_msg = ChatMessage(role=MessageRole.USER, content=query)
        assistant_msg = ChatMessage(
            role=MessageRole.ASSISTANT, content=state["draft_answer"]
        )
        self._history.append_messages(
            session_id, [user_msg, assistant_msg], self._session_ttl
        )
