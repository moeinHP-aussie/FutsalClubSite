# ══════════════════════════════════════════════════════════════════
#  Dockerfile  —  سیستم مدیریت باشگاه فوتسال
#  Multi-stage build: builder → runtime
#  Python 3.12 | Django 4.2 | Gunicorn | Redis-ready
# ══════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libffi-dev \
        libssl-dev \
        libjpeg-dev \
        libwebp-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a prefix (no system pollution)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Labels
LABEL maintainer="Futsal Club Dev Team"
LABEL description="Futsal Club Management System — Django 4.2"

# Runtime system libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libjpeg62-turbo \
        libwebp7 \
        curl \
        gettext \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1001 django && \
    useradd  --uid 1001 --gid django --shell /bin/bash --create-home django

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# App directory
WORKDIR /app

# Copy project source
COPY --chown=django:django . .

# Create required directories
RUN mkdir -p \
        /app/staticfiles \
        /app/mediafiles \
        /app/logs \
    && chown -R django:django /app

# Switch to non-root
USER django

# ── Environment defaults (override at runtime) ─────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=futsal_club.settings.production \
    PORT=8000 \
    WORKERS=3

# Expose port
EXPOSE 8000

# ── Healthcheck ───────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# ── Entrypoint ────────────────────────────────────────────────────
COPY --chown=django:django docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
