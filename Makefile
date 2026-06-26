.PHONY: help install dev lint format test up down clean

help:
	@echo "Industrial Brain OS Task Runner"
	@echo "Available commands:"
	@echo "  install   - Install backend, frontend, and shared dependencies"
	@echo "  dev       - Start backend and frontend in development mode"
	@echo "  lint      - Lint the codebase (Python and TypeScript)"
	@echo "  format    - Format the codebase (Python and TypeScript)"
	@echo "  test      - Run backend unit tests"
	@echo "  up        - Spin up docker infrastructure services (Postgres, Neo4j, Qdrant, Redis, MinIO)"
	@echo "  down      - Shut down docker infrastructure services"
	@echo "  clean     - Clean build, cache, and temporary files"

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

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.py[co]" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "node_modules" -exec rm -rf {} +
	find . -type d -name "dist" -exec rm -rf {} +
	find . -type d -name "build" -exec rm -rf {} +
