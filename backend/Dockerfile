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


# The Rijkshuisstijl files a document may use: the Rijkslint with the coat of
# arms, and the typeface. They come from the design system package, at the
# version the frontend uses (frontend/package.json; a test keeps the two
# equal). They are in the image so that an organisation that may carry them
# can point LETTERHEAD_LOGO_PATH and DOCUMENT_FONT_DIR here; nothing uses them
# until those settings are set. Their terms are in huisstijl/NOTICES.md: the
# logo and the typeface are for the Rijksoverheid and those working on its
# behalf only.
FROM node:22-slim AS huisstijl
ARG NLDD_DESIGN_SYSTEM_VERSION=0.8.96
WORKDIR /pkg
RUN npm pack "@nldd/design-system@${NLDD_DESIGN_SYSTEM_VERSION}" --silent \
    && tar -xzf nldd-design-system-*.tgz \
    && mkdir -p /huisstijl/fonts \
    && cp package/dist/favicon.svg /huisstijl/rijkslogo.svg \
    && cp package/dist/fonts/RijksSansWeb-Regular.woff2 \
          package/dist/fonts/RijksSansWeb-Italic.woff2 /huisstijl/fonts/ \
    && cp package/NOTICES.md /huisstijl/NOTICES.md


FROM python:3.13-slim

# uv is only needed for the reload setup in docker-compose; the entrypoint
# uses the venv directly.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Text layout for the PDF of a quote (WeasyPrint needs pango), and a
# sans-serif to fall back on when no huisstijl typeface is configured.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1001 appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app
COPY --from=huisstijl --chown=appuser:appuser /huisstijl /app/huisstijl

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
