# Build context: the repository ROOT (docker compose sets `context: .`),
# so the shared package and the backend's ai/ontology assets are reachable.

# Stage 1: Build dependencies
FROM python:3.9-slim AS builder

WORKDIR /build

# Install compilation dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
# Shared python package — the editable `-e ../shared/python` in
# requirements.txt resolves to /shared/python from the /build CWD.
COPY shared/python /shared/python

RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.9-slim AS runner

WORKDIR /app

# Create non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -r -u 10001 -g appgroup appuser

# Copy installed python dependencies from builder
COPY --from=builder --chown=appuser:appgroup /root/.local /home/appuser/.local
COPY --from=builder --chown=appuser:appgroup /shared/python /shared/python

# Application code, AI prompts/tools, and the ontology schema. The Celery
# worker needs ai/ and ontology/ at runtime, not just app/.
COPY --chown=appuser:appgroup backend/app /app/app
COPY --chown=appuser:appgroup backend/ai /app/ai
COPY --chown=appuser:appgroup ontology /app/ontology

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app

USER appuser

EXPOSE 8000

# Default: API server. The Celery worker service overrides this command
# (celery -A app.worker worker) using the same image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
