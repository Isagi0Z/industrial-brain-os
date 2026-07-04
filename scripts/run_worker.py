"""Start the Celery ingestion worker (local-dev convenience).

The API accepts document uploads and dispatches a parse -> embed -> kg Celery
chain onto the ``ingestion`` queue, but **a worker must be running to consume
it**. Without one, uploads sit in ``QUEUED`` forever and are never indexed.

Run it (using the backend virtualenv's Python) in its own terminal, alongside
the API and frontend::

    python scripts/run_worker.py

``--pool=solo`` keeps it single-process so it behaves identically on Windows
(which cannot ``fork``) and POSIX. In production the ``ib_worker`` container
runs the same command with the prefork pool for concurrency (docker compose).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"


def main() -> int:
    cmd = [
        sys.executable,
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
