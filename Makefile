.PHONY: help install dev lint format test up down clean db-migrate db-reset init-infra

help:
	@echo "Industrial Brain OS Task Runner"
	@echo "Available commands:"
	@echo "  install      - Install backend, frontend, and shared dependencies"
	@echo "  dev          - Start backend and frontend in development mode"
	@echo "  lint         - Lint the codebase (Python and TypeScript)"
	@echo "  format       - Format the codebase (Python and TypeScript)"
	@echo "  test         - Run backend unit tests"
	@echo "  up           - Spin up docker infrastructure services"
	@echo "  down         - Shut down docker infrastructure services"
	@echo "  db-migrate   - Apply all pending Alembic database migrations"
	@echo "  db-reset     - Drop and re-apply all migrations (destroys data)"
	@echo "  init-infra   - Initialise Qdrant/Neo4j/MinIO (run after docker up)"
	@echo "  clean        - Clean build, cache, and temporary files"

install:
	pip install -r backend/requirements.txt
	pip install -e shared/python
	cd frontend && pnpm install

dev:
	@echo "Starting development environment..."
	@echo "Please start the backend (cd backend && uvicorn app.main:app --reload) and frontend (cd frontend && pnpm run dev) separately."

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
