"""M20 architecture-compliance tests (ADR-013 — Clean Architecture).

Guards the dependency rule at the layer that matters most: the ``domain`` layer
must depend on nothing outward. If a future change imports an adapter or a
framework into a domain module, this test fails — turning an architecture
convention into an enforced invariant.
"""

from __future__ import annotations

import ast
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "app"
_DOMAIN = _APP / "domain"

# Outward layers / frameworks the domain must never import.
_FORBIDDEN_PREFIXES = (
    "app.infrastructure",
    "app.presentation",
    "app.application",
    "fastapi",
    "starlette",
    "sqlalchemy",
    "psycopg2",
    "neo4j",
    "qdrant_client",
    "redis",
    "celery",
)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                mods.append(node.module)
    return mods


def test_domain_layer_has_no_outward_imports():
    violations: list[str] = []
    for py in _DOMAIN.rglob("*.py"):
        for mod in _imported_modules(py):
            if any(mod == p or mod.startswith(p + ".") for p in _FORBIDDEN_PREFIXES):
                rel = py.relative_to(_APP.parent).as_posix()
                violations.append(f"{rel} imports '{mod}'")
    assert (
        not violations
    ), "domain layer must not import outward (ADR-013):\n" + "\n".join(violations)


def test_domain_layer_is_non_empty():
    # Guard against the test silently passing because the path is wrong.
    assert list(_DOMAIN.rglob("*.py")), "no domain modules found — check the path"
