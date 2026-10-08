#!/bin/sh
# A local Bouwmeester next to the local grip, run from a checkout of the
# Bouwmeester repository on the branch that has corpus-context and the card
# "Opdrachten in grip" (feat/opdrachten-bij-node). See docs/lokaal.md.
#
#   BOUWMEESTER_DIR=<checkout> ./bouwmeester.sh up      database, migrations, seed, backend, corpus-context, frontend
#   ./bouwmeester.sh status | logs | down | nuke
#
# Nothing of Bouwmeester is built into an image: backend and frontend run
# on the host from the checkout, so the checkout needs `uv sync` in backend/
# and `npm install` in frontend/ once. Only the database is a container.
# Ports are chosen so that a Bouwmeester stack of your own (5433, 8000, 5173)
# is left alone.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
state="$here/state/bouwmeester"
mkdir -p "$state"

DB_PORT=9201
BACKEND_PORT=9210
FEDERATION_PORT=9211
FRONTEND_PORT=9220
# Where Bouwmeester finds "its outway". Locally that is the dev outway of
# grip (grip.dev.dev_outway); in the FSC environment the outway of peer C.
OUTWAY_URL="${BOUWMEESTER_OUTWAY_URL:-http://localhost:9230}"

# The base of every node URI. It looks like a durable domain and is
# obviously local: nothing resolves it, grip reaches the corpus through its
# outway, as it would in production.
CORPUS_BASE_URI="https://corpus.voorbeeldministerie.localhost"

dir_file="$state/checkout"
if [ -n "${BOUWMEESTER_DIR:-}" ]; then
    (cd "$BOUWMEESTER_DIR" && pwd) > "$dir_file"
fi
checkout() {
    [ -f "$dir_file" ] || { echo "Set BOUWMEESTER_DIR to the checkout of Bouwmeester." >&2; exit 1; }
    cat "$dir_file"
}

export DATABASE_URL="postgresql+asyncpg://bouwmeester:bouwmeester@localhost:$DB_PORT/bouwmeester"
export DEV_NO_AUTH=1
export SESSION_SECRET_KEY=lokale-omgeving-geen-geheim
export FRONTEND_URL="http://localhost:$FRONTEND_PORT"
export BACKEND_URL="http://localhost:$BACKEND_PORT"
export CORPUS_BASE_URI
export CORPUS_NAME="Corpus Voorbeeldministerie (lokaal)"
# A real ministry identifier, because the contract asks for a TOOI URI; the
# corpus behind it is demo data.
export CORPUS_ORGANISATIE_TOOI_URI="https://identifier.overheid.nl/tooi/id/ministerie/mnre1034"
export FEDERATION_INBOUND_ENABLED=1
export FEDERATION_OUTBOUND_ENABLED=1
export FEDERATION_OUTWAY_URL="$OUTWAY_URL"
export FEDERATION_OUTBOUND_CACHE_SECONDS=5
# Nothing external: no language model, no chat, no syncs.
export LLM_PROVIDER=claude ANTHROPIC_API_KEY= MATTERMOST_ENABLED=false FCC_SYNC_ENABLED=false

start() { # name, directory, command...
    name="$1"; dir="$2"; shift 2
    if [ -f "$state/$name.pid" ] && kill -0 "$(cat "$state/$name.pid")" 2>/dev/null; then
        echo "  $name already running"; return
    fi
    (cd "$dir" && nohup "$@" > "$state/$name.log" 2>&1 < /dev/null & echo $! > "$state/$name.pid")
    echo "  $name started (log: state/bouwmeester/$name.log)"
}
stop() {
    for name in backend federation frontend; do
        if [ -f "$state/$name.pid" ]; then
            pid="$(cat "$state/$name.pid")"
            pkill -P "$pid" 2>/dev/null || true
            kill "$pid" 2>/dev/null || true
            rm -f "$state/$name.pid"
        fi
    done
}

case "${1:-status}" in
    up)
        bm="$(checkout)"
        docker compose -f "$here/bouwmeester/compose.yml" up -d --wait
        (cd "$bm/backend" && uv run alembic upgrade head)
        if [ ! -f "$state/seeded" ]; then
            # The seed of the repository itself. Without the key for its
            # encrypted person list it generates placeholder persons.
            (cd "$bm/backend" && uv run python scripts/seed.py) && touch "$state/seeded"
        fi
        start backend "$bm/backend" uv run uvicorn bouwmeester.core.app:create_app --factory --port "$BACKEND_PORT"
        # corpus-context is an application of its own. In production only the
        # inway reaches it; here it listens on localhost for the dev outway.
        start federation "$bm/backend" uv run uvicorn bouwmeester.federation.app:create_federation_app --factory --host 0.0.0.0 --port "$FEDERATION_PORT"
        start frontend "$bm/frontend" env VITE_API_URL="http://localhost:$BACKEND_PORT" npx vite --port "$FRONTEND_PORT" --strictPort
        "$0" status
        ;;
    status)
        echo "  Bouwmeester            http://localhost:$FRONTEND_PORT"
        echo "  backend                http://localhost:$BACKEND_PORT"
        echo "  corpus-context         http://localhost:$FEDERATION_PORT   (trusts the peer header; local only)"
        echo "  corpus base URI        $CORPUS_BASE_URI"
        for name in backend federation frontend; do
            if [ -f "$state/$name.pid" ] && kill -0 "$(cat "$state/$name.pid")" 2>/dev/null; then
                echo "  $name: running"
            else
                echo "  $name: stopped"
            fi
        done
        ;;
    logs) tail -n 40 -f "$state"/*.log ;;
    env)
        # For scripts that need the same settings (peer registration).
        env | grep -E '^(DATABASE_URL|DEV_NO_AUTH|CORPUS_|FEDERATION_|SESSION_SECRET_KEY)' ;;
    down)
        stop
        docker compose -f "$here/bouwmeester/compose.yml" stop ;;
    nuke)
        stop
        docker compose -f "$here/bouwmeester/compose.yml" down -v
        rm -rf "$state" ;;
    *) sed -n '2,13p' "$0"; exit 64 ;;
esac
