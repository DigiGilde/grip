FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# A patient, less parallel download: the default settings time out on slow
# or filtered networks, and a build that fails halfway is the costly case.
# Copy mode because the cache mount lives on another filesystem.
ENV UV_HTTP_TIMEOUT=120 \
    UV_CONCURRENT_DOWNLOADS=4 \
    UV_LINK_MODE=copy

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.13-slim

# uv is only needed for the reload setup in docker-compose; the entrypoint
# uses the venv directly.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN useradd --create-home --uid 1001 appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app

USER 1001

ENV PATH="/app/.venv/bin:$PATH"
# Unbuffered, so log lines and tracebacks reach the container log at once.
ENV PYTHONUNBUFFERED=1

ARG GIT_SHA=""
ARG BUILD_TIME=""
ENV GIT_SHA=$GIT_SHA
ENV BUILD_TIME=$BUILD_TIME

# 8080: the application. 8090: the federation listener, which must only be
# reachable from the FSC inway.
EXPOSE 8080 8090

# The process is chosen with GRIP_PROCESS or the first argument:
# web (default), federation, worker or all. See entrypoint.sh.
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
