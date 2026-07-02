"""Shared multi-strategy JSON extraction for LLM responses.

Extracted (architecture-refactor phase) from the RCA (M12) and Compliance
(M11) tool registries, which carried byte-identical copies of these helpers
(the Compliance registry's inline ``_try_bracket_extract`` was exactly
``balanced_extract(text, "[", "]")``). Behaviour is unchanged; only the
duplication is removed. The three-stage strategy mirrors M7's
``llm_relation_extractor`` (direct parse → balanced-bracket extraction →
code-fence stripping).

Note: the M7 extraction module keeps its own copy of these helpers; it is
outside the agent layer this refactor targets (it belongs to the ingestion/
KG pipeline) and its own tests import those names directly, so it is left
untouched here.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def try_direct(text: str) -> Optional[Any]:
    """Attempt a direct ``json.loads``; return None on failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def balanced_extract(text: str, open_ch: str, close_ch: str) -> Optional[Any]:
    """Find the first balanced ``open_ch`` … ``close_ch`` block and parse it."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def try_bracket_extract(text: str) -> Optional[Any]:
    """Parse the first balanced ``[`` … ``]`` array block."""
    return balanced_extract(text, "[", "]")


def try_brace_extract(text: str) -> Optional[Any]:
    """Parse the first balanced ``{`` … ``}`` object block."""
    return balanced_extract(text, "{", "}")


def try_strip_fences(text: str) -> Optional[Any]:
    """Remove ``` code fences and retry ``json.loads``."""
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
