"""M18 PromptOps unit tests.

Verifies the PromptLoader contract (schema validation, strict variable
injection, manifest consistency) and that every shipped prompt validates —
the same guarantees the CI gate (`scripts/validate_prompts.py`) enforces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.prompts.prompt_loader import (
    PromptLoader,
    PromptValidationError,
)

_PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "ai" / "prompts"


@pytest.fixture()
def loader() -> PromptLoader:
    return PromptLoader(_PROMPTS_ROOT)


def test_valid_prompt_loads_and_exposes_metadata(loader: PromptLoader):
    spec = loader.load_file("knowledge_brain/synthesize_answer.yaml")
    assert spec.prompt_id == "knowledge_brain.synthesize_answer"
    assert spec.version == "1.0"
    assert spec.owning_brain == "knowledge_brain"
    assert spec.output_format == "markdown"
    assert spec.description


def test_render_injects_variables(loader: PromptLoader):
    spec = loader.load_file("evaluation/faithfulness.yaml")
    rendered = loader.render(spec, "user_template", context="C-TEXT", answer="A-TEXT")
    assert "C-TEXT" in rendered and "A-TEXT" in rendered
    assert "{context}" not in rendered and "{answer}" not in rendered


def test_render_missing_variable_raises(loader: PromptLoader):
    spec = loader.load_file("evaluation/faithfulness.yaml")
    with pytest.raises(PromptValidationError) as exc:
        loader.render(spec, "user_template", context="only-context")
    assert "answer" in str(exc.value)


def test_invalid_schema_raises(loader: PromptLoader):
    # Missing required metadata (prompt_id/version/owning_brain/output_format).
    with pytest.raises(PromptValidationError):
        loader._validate(  # type: ignore[attr-defined]
            {"system": "You are a bot."}, source="bad.yaml"
        )


def test_missing_file_raises(loader: PromptLoader):
    with pytest.raises(PromptValidationError):
        loader.load_file("does_not_exist.yaml")


def test_bad_prompt_id_pattern_rejected(loader: PromptLoader):
    with pytest.raises(PromptValidationError):
        loader._validate(  # type: ignore[attr-defined]
            {
                "prompt_id": "NotDotted",
                "version": "1.0",
                "description": "long enough description",
                "owning_brain": "chat",
                "output_format": "markdown",
                "system": "x",
            },
            source="inline",
        )


def test_bad_version_pattern_rejected(loader: PromptLoader):
    with pytest.raises(PromptValidationError):
        loader._validate(  # type: ignore[attr-defined]
            {
                "prompt_id": "chat.thing",
                "version": "v1",
                "description": "long enough description",
                "owning_brain": "chat",
                "output_format": "markdown",
                "system": "x",
            },
            source="inline",
        )


def test_every_shipped_prompt_validates(loader: PromptLoader):
    files = [p for p in _PROMPTS_ROOT.rglob("*.yaml") if p.name != "MANIFEST.yaml"]
    assert len(files) == 13
    for path in files:
        rel = path.relative_to(_PROMPTS_ROOT).as_posix()
        spec = loader.load_file(rel)  # raises if invalid
        assert spec.prompt_id


def test_manifest_matches_disk(loader: PromptLoader):
    manifest = loader.load_manifest()
    manifest_ids = {e["prompt_id"] for e in manifest}
    disk_ids = {
        loader.load_file(p.relative_to(_PROMPTS_ROOT).as_posix()).prompt_id
        for p in _PROMPTS_ROOT.rglob("*.yaml")
        if p.name != "MANIFEST.yaml"
    }
    assert manifest_ids == disk_ids
    # Every manifest path resolves to a real file.
    for entry in manifest:
        assert (_PROMPTS_ROOT / entry["path"]).is_file()
