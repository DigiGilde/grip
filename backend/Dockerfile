FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev


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

EXPOSE 8080

ENTRYPOINT ["sh", "/app/entrypoint.sh"]
