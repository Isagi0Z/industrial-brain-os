"""PromptLoader — the canonical, schema-validated prompt service (M18, ADR-020).

Finalizes PromptOps: every prompt under ``ai/prompts/`` is loaded through this
service, validated against ``prompt_schema.json``, and rendered with strict
``{variable}`` injection. A prompt that fails the schema, or a render call that
is missing a variable the template references, raises ``PromptValidationError``
rather than failing silently (Engineering Bible §1 — no silent failures).

Backward compatibility: this service does **not** replace the per-brain
loaders (``agents/base.load_prompt``, ``llm_judge``, ``YamlPromptLoader``) —
those continue to read the same YAML files unchanged. PromptLoader is the
validated superset used by the CI gate (``scripts/validate_prompts.py``), the
unit tests, and any new consumer that wants schema + variable safety.

The body of a prompt is its ``system`` instruction plus one or more
``*_template`` fields whose names stay as the existing consumers expect
(``user_template``, ``context_template``, ``extraction_template``,
``uncertain_template``, ``no_context_template``).
"""

from __future__ import annotations

import json
import logging
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class PromptValidationError(Exception):
    """Raised when a prompt fails schema validation, references an unknown
    file, or is rendered without a variable its template requires."""


@dataclass(frozen=True)
class PromptSpec:
    """A validated prompt: its metadata plus the raw field mapping."""

    prompt_id: str
    version: str
    description: str
    owning_brain: str
    output_format: str
    data: Dict[str, Any]

    def field(self, name: str) -> str:
        value = self.data.get(name)
        if not isinstance(value, str):
            raise PromptValidationError(
                f"prompt '{self.prompt_id}' has no string field '{name}'"
            )
        return value


def _template_variables(template: str) -> Set[str]:
    """Return the set of ``{name}`` placeholders referenced by a template."""
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name
    }


class PromptLoader:
    """Loads and validates prompts from the ``ai/prompts`` tree.

    ``prompts_root`` is the directory holding the prompt YAMLs and
    ``prompt_schema.json``. The JSON Schema is loaded once; each prompt is
    validated on load and cached by ``prompt_id``.
    """

    def __init__(self, prompts_root: Path, schema_path: Path | None = None) -> None:
        self._root = prompts_root
        self._schema_path = schema_path or (prompts_root / "prompt_schema.json")
        self._schema: Dict[str, Any] = self._load_schema()
        self._cache: Dict[str, PromptSpec] = {}

    def _load_schema(self) -> Dict[str, Any]:
        try:
            with self._schema_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError as exc:
            raise PromptValidationError(
                f"prompt schema not found at {self._schema_path}"
            ) from exc

    def load_file(self, relative_path: str) -> PromptSpec:
        """Load and validate a single prompt YAML by path relative to the
        prompts root (e.g. ``knowledge_brain/synthesize_answer.yaml``)."""
        path = self._root / relative_path
        if not path.is_file():
            raise PromptValidationError(f"prompt file not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise PromptValidationError(f"prompt {relative_path} is not a mapping")
        spec = self._validate(data, source=relative_path)
        self._cache[spec.prompt_id] = spec
        return spec

    def _validate(self, data: Dict[str, Any], source: str) -> PromptSpec:
        # Local import so the module imports even if jsonschema is absent; a
        # missing validator is a hard error only when validation is requested.
        try:
            import jsonschema  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - jsonschema is a declared dep
            raise PromptValidationError(
                "jsonschema is required to validate prompts"
            ) from exc

        try:
            jsonschema.validate(instance=data, schema=self._schema)
        except jsonschema.ValidationError as exc:
            raise PromptValidationError(
                f"prompt {source} failed schema validation: {exc.message}"
            ) from exc

        return PromptSpec(
            prompt_id=data["prompt_id"],
            version=str(data["version"]),
            description=data["description"],
            owning_brain=data["owning_brain"],
            output_format=data["output_format"],
            data=data,
        )

    def render(self, spec: PromptSpec, field: str, **variables: Any) -> str:
        """Render a prompt field with ``{variable}`` injection.

        Raises ``PromptValidationError`` if the template references a variable
        that was not supplied — never emits a half-substituted prompt."""
        template = spec.field(field)
        required = _template_variables(template)
        missing = sorted(required - set(variables))
        if missing:
            raise PromptValidationError(
                f"cannot render '{spec.prompt_id}.{field}': missing variables "
                f"{missing}"
            )
        return template.format(**variables)

    def load_manifest(self, manifest_path: Path | None = None) -> List[Dict[str, Any]]:
        """Load the prompt MANIFEST inventory (list of prompt entries)."""
        path = manifest_path or (self._root / "MANIFEST.yaml")
        if not path.is_file():
            raise PromptValidationError(f"manifest not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh) or {}
        prompts = manifest.get("prompts", [])
        if not isinstance(prompts, list):
            raise PromptValidationError("manifest 'prompts' must be a list")
        return prompts

    def template_fields(self, spec: PromptSpec) -> List[str]:
        """Return the names of the renderable ``*_template`` fields present."""
        return [
            key
            for key, value in spec.data.items()
            if key.endswith("_template") and isinstance(value, str)
        ]
