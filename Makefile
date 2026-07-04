.PHONY: help install dev worker lint format test up down clean db-migrate db-reset init-infra eval validate-prompts demo-data security-audit benchmark coverage

help:
	@echo "Industrial Brain OS Task Runner"
	@echo "Available commands:"
	@echo "  install      - Install backend, frontend, and shared dependencies"
	@echo "  dev          - Start backend and frontend in development mode"
	@echo "  worker       - Start the Celery ingestion worker (required to process uploads)"
	@echo "  lint         - Lint the codebase (Python and TypeScript)"
	@echo "  format       - Format the codebase (Python and TypeScript)"
	@echo "  test         - Run backend unit tests"
	@echo "  eval         - Run the RAG evaluation suite (M16) and write the baseline"
	@echo "  validate-prompts - Validate all prompt YAMLs against the schema + manifest (M18)"
	@echo "  demo-data    - Seed the demo knowledge graph + generate demo PDFs (M19)"
	@echo "  security-audit - Run bandit + pip-audit + pnpm audit (M20)"
	@echo "  benchmark    - Run the API latency benchmark (M20, NFR-03)"
	@echo "  coverage     - Run the test suite with coverage (M20)"
	@echo "  up           - Spin up docker infrastructure services"
	@echo "  down         - Shut down docker infrastructure services"
	@echo "  db-migrate   - Apply all pending Alembic database migrations"
	@echo "  db-reset     - Drop and re-apply all migrations (destroys data)"
	@echo "  init-infra   - Initialise Qdrant/Neo4j/MinIO (run after docker up)"
	@echo "  clean        - Clean build, cache, and temporary files"

eval:
	python scripts/run_eval.py

validate-prompts:
	python scripts/validate_prompts.py

demo-data:
	python scripts/load_demo_data.py

security-audit:
	cd backend && bandit -r app -ll
	cd backend && pip-audit || true
	cd frontend && pnpm audit --audit-level high

benchmark:
	python scripts/benchmark_latency.py

coverage:
	cd backend && pytest --cov=app --cov-report=term-missing

install:
	pip install -r backend/requirements.txt
	pip install -e shared/python
	cd frontend && pnpm install

dev:
	@echo "Starting development environment..."
	@echo "Run these THREE processes in separate terminals:"
	@echo "  1. Backend:  cd backend && uvicorn app.main:app --reload"
	@echo "  2. Worker:   make worker    (REQUIRED — without it, uploaded documents stay QUEUED and are never indexed)"
	@echo "  3. Frontend: cd frontend && pnpm run dev"

# Celery ingestion worker (M15, ADR-015). Consumes the `ingestion` queue and runs
# the parse -> embed -> kg pipeline for each uploaded document. Without a running
# worker the API accepts uploads but they remain QUEUED forever. `--pool=solo`
# keeps it single-process so it works identically on Windows and POSIX; scale out
# in production via the `ib_worker` container (docker compose).
# Uses scripts/run_worker.py rather than a bare `celery` invocation because a
# plain `celery -A app.worker worker` resolves through whatever is first on
# PATH — on a machine with multiple Python installs that is easy to get wrong
# (a global interpreter missing project deps fails with a confusing
# ModuleNotFoundError deep in app startup). The script always re-execs through
# the backend venv's interpreter regardless of PATH.
worker:
	python scripts/run_worker.py

lint:
	cd backend && black --check app tests
	cd backend && ruff check app tests
	cd frontend && pnpm run lint

format:
	cd backend && black app tests
	cd backend && ruff check --fix app tests
	cd frontend && pnpm run format

test:
	cd backend && pytest

up:
	docker compose up -d

down:
	docker compose down

db-migrate:
	cd backend && alembic upgrade head

db-reset:
	cd backend && alembic downgrade base && alembic upgrade head

init-infra:
	python scripts/init_infra.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.py[co]" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "node_modules" -exec rm -rf {} +
	find . -type d -name "dist" -exec rm -rf {} +
	find . -type d -name "build" -exec rm -rf {} +
