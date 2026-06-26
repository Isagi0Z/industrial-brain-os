# Stage 1: Build dependencies
FROM python:3.9-slim AS builder

WORKDIR /build

# Install compilation dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Copy shared python package directory to build context
COPY ../shared/python /shared/python

RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.9-slim AS runner

WORKDIR /app

# Create non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -r -u 10001 -g appgroup appuser

# Copy installed python dependencies from builder
COPY --from=builder --chown=appuser:appgroup /root/.local /home/appuser/.local
# Copy code files
COPY --chown=appuser:appgroup ./app /app/app
# Copy shared python package
COPY --from=builder --chown=appuser:appgroup /shared/python /shared/python

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
