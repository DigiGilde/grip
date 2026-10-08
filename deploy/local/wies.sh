#!/bin/sh
# A local Wies next to the local grip, run from a checkout of the Wies
# repository on the branch with the link to grip (feat/grip-koppeling).
# See docs/lokaal.md and docs/wies.md.
#
#   WIES_DIR=<checkout> ./wies.sh up     database, migrations, dummy data, web
#   ./wies.sh sync                       Wies pulls opdrachten, roles and placements from grip
#   ./wies.sh env                        the environment for the grip backend
#   ./wies.sh manage <args>              manage.py with the local settings
#   ./wies.sh status | down | nuke
#
# Wies runs on the host from the checkout (needs `uv sync` there once);
# only the database is a container. The two keys of the link are generated
# into state/wies/keys.env, which is not in the repo.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
state="$here/state/wies"
mkdir -p "$state"

DB_PORT=9301
WEB_PORT=9310
# The address on which /api of grip answers, as Wies reaches it.
GRIP_URL="${GRIP_URL:-http://localhost:8010}"

dir_file="$state/checkout"
if [ -n "${WIES_DIR:-}" ]; then
    (cd "$WIES_DIR" && pwd) > "$dir_file"
fi
checkout() {
    [ -f "$dir_file" ] || { echo "Set WIES_DIR to the checkout of Wies." >&2; exit 1; }
    cat "$dir_file"
}

if [ ! -f "$state/keys.env" ]; then
    {
        echo "GRIP_READ_API_KEY=$(openssl rand -hex 24)"
        echo "GRIP_EXPORT_KEY=$(openssl rand -hex 24)"
    } > "$state/keys.env"
    chmod 600 "$state/keys.env"
fi
# shellcheck disable=SC1091
. "$state/keys.env"

export DJANGO_SETTINGS_MODULE=config.settings.local
export POSTGRES_HOST=localhost POSTGRES_PORT="$DB_PORT" POSTGRES_USER=wies POSTGRES_PASSWORD=wies POSTGRES_DB=wies
# No identity provider: Wies logs you in as the first super admin.
export SKIP_OIDC=true
export INITIAL_USER_FIRSTNAME=Test INITIAL_USER_LASTNAME=Beheerder INITIAL_USER_EMAIL=testbeheerder@grip.invalid
export GRIP_BASE_URL="$GRIP_URL" GRIP_EXPORT_KEY GRIP_READ_API_KEY
export SITE_BASE_URL="http://localhost:$WEB_PORT"

manage() { (cd "$(checkout)" && uv run python manage.py "$@"); }

case "${1:-status}" in
    up)
        docker compose -f "$here/wies/compose.yml" up -d --wait
        manage migrate --noinput
        if [ ! -f "$state/seeded" ]; then
            manage setup
            # The small, offline profile of Wies's own dummy data.
            manage load_dummy_data --profile base
            manage ensure_initial_user || true
            touch "$state/seeded"
        fi
        if [ -f "$state/web.pid" ] && kill -0 "$(cat "$state/web.pid")" 2>/dev/null; then
            echo "  web already running"
        else
            (cd "$(checkout)" && nohup uv run python manage.py runserver "$WEB_PORT" --noreload > "$state/web.log" 2>&1 < /dev/null & echo $! > "$state/web.pid")
            echo "  web started (log: state/wies/web.log)"
        fi
        "$0" status
        ;;
    sync) manage sync_grip ;;
    manage) shift; manage "$@" ;;
    env)
        echo "WIES_BASE_URL=http://localhost:$WEB_PORT"
        echo "WIES_API_KEY=$GRIP_READ_API_KEY"
        echo "GRIP_EXPORT_KEY=$GRIP_EXPORT_KEY"
        ;;
    status)
        echo "  Wies                   http://localhost:$WEB_PORT"
        echo "  pulls from grip at     $GRIP_URL"
        if [ -f "$state/web.pid" ] && kill -0 "$(cat "$state/web.pid")" 2>/dev/null; then echo "  web: running"; else echo "  web: stopped"; fi
        ;;
    down)
        if [ -f "$state/web.pid" ]; then
            pid="$(cat "$state/web.pid")"; pkill -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; rm -f "$state/web.pid"
        fi
        docker compose -f "$here/wies/compose.yml" stop ;;
    nuke)
        "$0" down || true
        docker compose -f "$here/wies/compose.yml" down -v
        rm -rf "$state" ;;
    *) sed -n '2,15p' "$0"; exit 64 ;;
esac
