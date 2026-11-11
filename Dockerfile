# BayiOS production image.
# Build: podman build -t bayios:latest .
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
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-group dev --no-install-project

# Layer 2: source, migrations, and the installed project itself.
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
RUN uv sync --frozen --no-group dev

ENV PATH="/app/.venv/bin:$PATH"

# Bind to all interfaces inside the container; the LAN port is published by compose.
ENV BAYIOS_HOST=0.0.0.0 \
    BAYIOS_PORT=8000

EXPOSE 8000

CMD ["bayios"]
