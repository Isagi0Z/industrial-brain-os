"""Start the Celery ingestion worker (local-dev convenience).

The API accepts document uploads and dispatches a parse -> embed -> kg Celery
chain onto the ``ingestion`` queue, but **a worker must be running to consume
it**. Without one, uploads sit in ``QUEUED`` forever and are never indexed.

Run it in its own terminal, alongside the API and frontend, with ANY Python on
your PATH — this script always re-execs itself through the backend
virtualenv's interpreter, so it can't silently fall back to a global Python
that is missing project dependencies (langgraph, celery, etc.)::

    python scripts/run_worker.py

``--pool=solo`` keeps it single-process so it behaves identically on Windows
(which cannot ``fork``) and POSIX. In production the ``ib_worker`` container
runs the same command with the prefork pool for concurrency (docker compose).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
VENV_DIR = BACKEND_DIR / "venv"
VENV_PYTHON = VENV_DIR / (
    "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
)


def _resolve_python() -> str:
    """Always use the backend venv's interpreter, never whatever `python`
    happens to resolve to on the caller's PATH — a global interpreter is
    missing project dependencies (langgraph, celery, sentence-transformers,
    ...) and fails with a confusing ModuleNotFoundError deep in app startup."""
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    print(
        f"WARNING: backend venv not found at {VENV_DIR} — falling back to "
        f"{sys.executable}. Run `make install` (or see INSTALLATION.md) to "
        "create it; otherwise this will likely fail with a missing module.",
        file=sys.stderr,
    )
    return sys.executable


def main() -> int:
    python = _resolve_python()
    cmd = [
        python,
        "-m",
        "celery",
        "-A",
        "app.worker",
        "worker",
        "--loglevel=info",
        "--queues=ingestion",
        "--pool=solo",
        "--concurrency=1",
    ]
    print(f"Starting ingestion worker:\n  {' '.join(cmd)}\n  (cwd={BACKEND_DIR})\n")
    try:
        return subprocess.call(cmd, cwd=str(BACKEND_DIR))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
