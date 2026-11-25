# BayiOS production image.
# Build: podman-compose build app (or podman build -t localhost/bayios:latest .)
FROM python:3.13-slim

# uv is the project's dependency manager (pyproject.toml + uv.lock).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Layer 1: dependencies only (from the lock file), excluding the dev group,
# so the image layer is cached until pyproject/uv.lock actually changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-group dev --no-install-project

# Layer 2: source, migrations, and the installed project itself.
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
RUN uv sync --frozen --no-group dev

# Build metadata is injected by scripts/update-bayios.ps1 (compose build args)
# and exposed by GET /health so an operator can prove which commit is running.
# Keep these after the dependency/source layers so a new BUILD_TIME does not
# invalidate the expensive uv sync cache layer.
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
LABEL org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_TIME}"
ENV BAYIOS_BUILD_SHA="${GIT_SHA}" \
    BAYIOS_BUILD_TIME="${BUILD_TIME}"

ENV PATH="/app/.venv/bin:$PATH"

# Bind to all interfaces inside the container; the LAN port is published by compose.
ENV BAYIOS_HOST=0.0.0.0 \
    BAYIOS_PORT=8000

EXPOSE 8000

CMD ["bayios"]
