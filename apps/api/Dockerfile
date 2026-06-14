# ── Build stage ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime stage ────────────────────────────────────────────────────
FROM python:3.12-slim

# Release version, passed by the release workflow; read at runtime via
# settings.app_version. Defaults to the dev sentinel for source builds.
ARG APP_VERSION=0.0.0-dev
ENV APP_VERSION=${APP_VERSION}

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r cmp && useradd -r -g cmp -d /app -s /sbin/nologin cmp

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

RUN chown -R cmp:cmp /app

USER cmp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the server. Database migrations and the initial-admin
# bootstrap are owned by a separate init container (see the OSS
# docker-compose in consentos-deployment) — the API assumes the
# schema is ready by the time it starts.
# Workers configurable via WEB_CONCURRENCY (default 4, use 1 for 256MB RAM)
CMD ["sh", "-c", "uvicorn src.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-4} \
    --access-log \
    --proxy-headers \
    --forwarded-allow-ips '*'"]
