#!/usr/bin/env python3
"""Standalone infrastructure initialisation script for Industrial Brain OS.

Usage (from repo root):
    python scripts/init_infra.py

Exits 0 on success, 1 on any failure.
Requires all five Docker services to be running.
"""
import sys
import os

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.infrastructure.logging.logger import setup_logging  # noqa: E402
from app.infrastructure.di.container import DIContainer  # noqa: E402
from app.infrastructure.database.infra_init import run_all  # noqa: E402

setup_logging()


def main() -> int:
    print("Industrial Brain OS — Infrastructure Init")
    print("=" * 45)

    container = DIContainer()
    failures: list[str] = []

    # --- connectivity checks ---
    print("\n[1/5] PostgreSQL ...", end=" ", flush=True)
    try:
        pg = container.get_postgres()
        with pg.cursor() as cur:
            cur.execute("SELECT 1;")
        print("OK")
    except Exception as exc:
        print(f"FAILED ({exc})")
        failures.append("PostgreSQL")
        pg = None

    print("[2/5] Neo4j     ...", end=" ", flush=True)
    try:
        neo4j = container.get_neo4j()
        print("OK")
    except Exception as exc:
        print(f"FAILED ({exc})")
        failures.append("Neo4j")
        neo4j = None

    print("[3/5] Qdrant    ...", end=" ", flush=True)
    try:
        qdrant = container.get_qdrant()
        print("OK")
    except Exception as exc:
        print(f"FAILED ({exc})")
        failures.append("Qdrant")
        qdrant = None

    print("[4/5] Redis     ...", end=" ", flush=True)
    try:
        container.get_redis()
        print("OK")
    except Exception as exc:
        print(f"FAILED ({exc})")
        failures.append("Redis")

    print("[5/5] MinIO     ...", end=" ", flush=True)
    try:
        minio = container.get_minio()
        print("OK")
    except Exception as exc:
        print(f"FAILED ({exc})")
        failures.append("MinIO")
        minio = None

    if failures:
        print(f"\n✗ Connectivity failures: {', '.join(failures)}")
        print("  Ensure all Docker services are running: docker compose up -d")
        return 1

    # --- infrastructure init ---
    print("\nInitialising infrastructure...")
    try:
        run_all(qdrant, neo4j, minio)
        print("✓ Qdrant collections ready.")
        print("✓ Neo4j constraints and indexes applied.")
        print("✓ MinIO buckets ready.")
    except Exception as exc:
        print(f"✗ Init failed: {exc}")
        return 1

    print("\n✓ All infrastructure initialised successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
