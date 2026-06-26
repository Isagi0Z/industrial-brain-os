# Industrial Brain OS

Industrial Brain OS is an AI-powered Unified Asset & Operations Brain designed for Industrial Knowledge Intelligence.

## Documentation Index
- [Architecture Blueprint (Version 1)](docs/industrial_brain_architecture.md)
- [Architecture Blueprint (Version 2)](docs/industrial_brain_architecture_v2.md)
- [Engineering Bible v1.0](docs/engineering_bible.md)
- [Architecture Decision Records (ADRs)](docs/architecture_decision_records.md)

---

## Project Structure

This project is set up as a monorepo containing:
- **`backend/`**: FastAPI-based Clean Architecture backend service.
- **`frontend/`**: React + Vite + TypeScript dashboard interface.
- **`shared/`**: Common assets, constants, configurations, and utilities shared between services.
  - `shared/python/`: Shared Python module (`industrial-brain-shared`).
  - `shared/ts/`: Shared npm package (`@industrial-brain/shared`).
- **`docker-compose.yml`**: Configures PostgreSQL, Neo4j, Qdrant, Redis, and MinIO database environments.

---

## Local Development Setup

### Prerequisites
- **Node.js** (>= v18.0) & **pnpm** (>= 8.0)
- **Python** (>= 3.9) & **pip**
- **Docker & Docker Compose**

### 1. Database Infrastructure Setup
To spin up all databases and external cache/storage services:
```bash
# Using docker compose
docker compose up -d
```
This launches:
- **PostgreSQL** (Port `5432`): Core transactional databases and metadata.
- **Neo4j Community** (Port `7474` / `7687`): Ontological Knowledge Graph.
- **Qdrant** (Port `6333`): Vector database for dense/sparse embedding search.
- **Redis** (Port `6379`): Cache, short-term history, and pub-sub broker.
- **MinIO** (Port `9000` / Console on `9001`): Object storage for documents.

### 2. Backend Setup
1. Create and activate a Python virtual environment:
   ```bash
   cd backend
   python -m venv venv
   # On Windows:
   venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Verify by opening the Swagger documentation: `http://localhost:8000/docs`.

### 3. Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   pnpm install
   ```
2. Run the Vite development server:
   ```bash
   pnpm run dev
   ```
3. Open `http://localhost:3000` to view the dashboard shell.

---

## Development Workflow

### Tasks and Utilities
Helper scripts and runners are provided for convenience:
- **Windows (PowerShell)**: `./run.ps1`
  - `./run.ps1 up` - start docker infrastructure
  - `./run.ps1 install` - install all package dependencies
  - `./run.ps1 lint` - run python (black, ruff) and typescript checkers
  - `./run.ps1 format` - auto-format python and typescript code
  - `./run.ps1 test` - execute backend tests
- **Unix/Linux (Make)**: `Makefile`
  - `make up` - start docker compose services
  - `make install` - install all dependencies
  - `make lint` - run code linting
  - `make format` - auto-format files
  - `make test` - execute pytest unit tests

### Branching and Commits
- **Branch Naming**: Keep branches short-lived and prefixed: `feature/<name>`, `bugfix/<name>`.
- **Commit Messages**: Follow [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat(<scope>): <description>`
  - `fix(<scope>): <description>`
  - `docs(<scope>): <description>`
