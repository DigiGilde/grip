#!/bin/sh
set -e

# Use the venv directly: `uv run` would try to re-install the project.
export PATH="/app/.venv/bin:$PATH"

# One image, several processes. GRIP_PROCESS (or the first argument) picks
# which one this container runs:
#
#   web         the application for people: migrations, then uvicorn on 8080
#   federation  the routes other organisations call, on 8090. Must only be
#               reachable from the FSC inway (see grip/federation/app.py)
#   worker      the background loops (outbox, inbox catch-up)
#   all         web plus, when federation is switched on, the listener and
#               the worker as child processes. For platforms that give an
#               instance a single backend container.
#
# Migrations run only in `web` and `all`, so that exactly one container per
# instance applies them. Set RUN_MIGRATIONS=0 to skip them there too.
PROCESS="${1:-${GRIP_PROCESS:-web}}"
WEB_PORT="${PORT:-8080}"
FEDERATION_PORT="${FEDERATION_PORT:-8090}"

migrate() {
    if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
        echo "Running database migrations..."
        alembic upgrade head
    fi
}

# X-Forwarded-* headers are handled by the application itself, which only
# believes the proxies named in TRUSTED_PROXIES. uvicorn's own handling is
# switched off so there is one place that decides.
web() {
    exec uvicorn grip.core.app:create_app --factory \
        --host 0.0.0.0 --port "$WEB_PORT" --no-proxy-headers
}

federation() {
    exec uvicorn grip.federation.app:app \
        --host 0.0.0.0 --port "$FEDERATION_PORT" --no-proxy-headers
}

worker() {
    exec python -m grip.worker
}

is_on() {
    case "$1" in
        1 | true | True | TRUE | yes | on) return 0 ;;
        *) return 1 ;;
    esac
}

case "$PROCESS" in
    web)
        migrate
        echo "Starting the application on port $WEB_PORT..."
        web
        ;;
    federation)
        echo "Starting the federation listener on port $FEDERATION_PORT..."
        federation
        ;;
    worker)
        echo "Starting the worker..."
        worker
        ;;
    all)
        migrate
        if is_on "${FEDERATION_INBOUND_ENABLED:-0}"; then
            echo "Starting the federation listener on port $FEDERATION_PORT..."
            uvicorn grip.federation.app:app \
                --host 0.0.0.0 --port "$FEDERATION_PORT" --no-proxy-headers &
        fi
        if is_on "${FEDERATION_INBOUND_ENABLED:-0}" || is_on "${FEDERATION_OUTBOUND_ENABLED:-0}"; then
            echo "Starting the worker..."
            python -m grip.worker &
        fi
        echo "Starting the application on port $WEB_PORT..."
        web
        ;;
    *)
        echo "Unknown process '$PROCESS'. Use web, federation, worker or all." >&2
        exit 64
        ;;
esac
