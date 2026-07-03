"""Prompt validation gate (M18, ADR-020) — `make validate-prompts`.

Fails the build (exit 1) when any of the following is true:

  1. a prompt YAML under ``backend/ai/prompts/`` fails the JSON Schema;
  2. the MANIFEST and the files on disk disagree (missing file, unlisted
     file, prompt_id/version mismatch, or a duplicate prompt_id);
  3. a prompt template cannot be rendered when every ``{placeholder}`` it
     references is supplied (a malformed template);
  4. a hardcoded prompt assignment (``system_prompt = "…"`` / ``system = "…"``)
     is found in the Python sources — prompts must live in YAML, not code.

This is the PromptOps CI gate; it runs in ``ci/prompts.yml`` on every PR.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _REPO_ROOT / "backend"
sys.path.insert(0, str(_BACKEND))

from app.infrastructure.prompts.prompt_loader import (  # noqa: E402
    PromptLoader,
    PromptValidationError,
)

_PROMPTS_ROOT = _BACKEND / "ai" / "prompts"
_HARDCODED_PATTERN = re.compile(
    r"""^\s*(system_prompt|system)\s*=\s*["'](You |You'|Answer |Respond )"""
)
_SCAN_DIRS = [_BACKEND / "app", _BACKEND / "ai"]


def _iter_prompt_files() -> list[Path]:
    return sorted(p for p in _PROMPTS_ROOT.rglob("*.yaml") if p.name != "MANIFEST.yaml")


def _validate_files(loader: PromptLoader, errors: list[str]) -> dict:
    """Validate every prompt file against the schema. Returns id -> spec."""
    by_id: dict = {}
    for path in _iter_prompt_files():
        rel = path.relative_to(_PROMPTS_ROOT).as_posix()
        try:
            spec = loader.load_file(rel)
        except PromptValidationError as exc:
            errors.append(f"[schema] {rel}: {exc}")
            continue
        if spec.prompt_id in by_id:
            errors.append(f"[duplicate] prompt_id '{spec.prompt_id}' used twice")
        by_id[spec.prompt_id] = (spec, rel)
    return by_id


def _check_manifest(loader: PromptLoader, by_id: dict, errors: list[str]) -> None:
    manifest = loader.load_manifest()
    manifest_ids = set()
    for entry in manifest:
        pid = entry.get("prompt_id")
        manifest_ids.add(pid)
        if pid not in by_id:
            errors.append(f"[manifest] '{pid}' listed but no matching file/prompt_id")
            continue
        spec, rel = by_id[pid]
        if entry.get("path") != rel:
            errors.append(
                f"[manifest] '{pid}' path '{entry.get('path')}' != actual '{rel}'"
            )
        if str(entry.get("version")) != spec.version:
            errors.append(
                f"[manifest] '{pid}' version '{entry.get('version')}' != "
                f"file version '{spec.version}'"
            )
        if entry.get("owning_brain") != spec.owning_brain:
            errors.append(f"[manifest] '{pid}' owning_brain mismatch vs file")
    for pid in by_id:
        if pid not in manifest_ids:
            errors.append(
                f"[manifest] prompt '{pid}' on disk but missing from MANIFEST"
            )


def _render_smoke_test(loader: PromptLoader, by_id: dict, errors: list[str]) -> None:
    """Every template must render when all its placeholders are supplied."""
    for pid, (spec, rel) in by_id.items():
        for field in loader.template_fields(spec):
            template = spec.field(field)
            variables = {name: "X" for name in _placeholders(template)}
            try:
                loader.render(spec, field, **variables)
            except PromptValidationError as exc:
                errors.append(f"[render] {rel}:{field}: {exc}")
            except (KeyError, ValueError, IndexError) as exc:
                errors.append(f"[render] {rel}:{field}: malformed template ({exc})")


def _placeholders(template: str):
    import string

    return {fn for _, fn, _, _ in string.Formatter().parse(template) if fn}


def _scan_hardcoded_prompts(errors: list[str]) -> None:
    for base in _SCAN_DIRS:
        for py in base.rglob("*.py"):
            if "__pycache__" in py.parts or "tests" in py.parts:
                continue
            for lineno, line in enumerate(
                py.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if _HARDCODED_PATTERN.match(line):
                    rel = py.relative_to(_REPO_ROOT).as_posix()
                    errors.append(f"[hardcoded] {rel}:{lineno}: {line.strip()}")


def main() -> int:
    errors: list[str] = []
    loader = PromptLoader(_PROMPTS_ROOT)

    by_id = _validate_files(loader, errors)
    _check_manifest(loader, by_id, errors)
    _render_smoke_test(loader, by_id, errors)
    _scan_hardcoded_prompts(errors)

    if errors:
        print("PROMPT VALIDATION FAILED:")
        for e in errors:
            print(f"  {e}")
        return 1

    print(
        f"PASS: {len(by_id)} prompts validated against schema + manifest; "
        f"all templates render; no hardcoded prompts."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
