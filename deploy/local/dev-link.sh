#!/bin/sh
# Connect the grip you develop on (backend on 8010, `just dev` style) to the
# local Bouwmeester WITHOUT FSC: a dev outway forwards the calls and sets
# the peer header, so both applications run their real federation code.
# See docs/lokaal.md, "Grip en Bouwmeester zonder FSC".
#
#   ./dev-link.sh up       dev outway (9230) and grip's federation listener (9231)
#   ./dev-link.sh peers    register grip in Bouwmeester and Bouwmeester in grip
#   ./dev-link.sh env      the environment for the grip backend on 8010
#   ./dev-link.sh status | down
#
# GRIP_DATABASE_URL says which grip database the listener reads; it must be
# the one of the backend on 8010. Default: the development database.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
state="$here/state/dev-link"
mkdir -p "$state"

OUTWAY_PORT=9230
GRIP_FEDERATION_PORT=9231
BOUWMEESTER_BACKEND=http://localhost:9210
BOUWMEESTER_FEDERATION=http://localhost:9211
STANDIN=http://localhost:8040
CORPUS_BASE_URI="https://corpus.voorbeeldministerie.localhost"

# Fictional peer ids. Not the ones of the FSC environment (…01, …02, …03),
# so the same Bouwmeester can know this grip and the grip of that environment.
GRIP_PEER_ID=01700000000000000011
BOUWMEESTER_PEER_ID=01700000000000000013
# Without FSC a grant hash is just a name both sides agree on.
GRANT_GRIP_TO_CORPUS=dev-grant-grip-naar-bouwmeester
GRANT_CORPUS_TO_GRIP=dev-grant-bouwmeester-naar-grip

db_file="$state/grip-database-url"
[ -n "${GRIP_DATABASE_URL:-}" ] && printf '%s\n' "$GRIP_DATABASE_URL" > "$db_file"
grip_db() {
    if [ -f "$db_file" ]; then cat "$db_file"; else echo "postgresql+asyncpg://grip:grip@localhost:5434/grip"; fi
}

start() { # name, directory, command...
    name="$1"; dir="$2"; shift 2
    if [ -f "$state/$name.pid" ] && kill -0 "$(cat "$state/$name.pid")" 2>/dev/null; then
        echo "  $name already running"; return
    fi
    (cd "$dir" && nohup "$@" > "$state/$name.log" 2>&1 < /dev/null & echo $! > "$state/$name.pid")
    echo "  $name started (log: state/dev-link/$name.log)"
}

case "${1:-status}" in
    up)
        cat > "$state/dev-outway.json" <<ROUTES
{
  "fallback": "$STANDIN",
  "routes": {
    "$GRANT_GRIP_TO_CORPUS": {
      "target": "$BOUWMEESTER_FEDERATION",
      "caller_peer_id": "$GRIP_PEER_ID",
      "note": "grip -> corpus-context of the local Bouwmeester"
    },
    "$GRANT_CORPUS_TO_GRIP": {
      "target": "http://localhost:$GRIP_FEDERATION_PORT",
      "caller_peer_id": "$BOUWMEESTER_PEER_ID",
      "note": "Bouwmeester -> grip-opdrachtverkeer of the local grip"
    }
  }
}
ROUTES
        start dev-outway "$repo/backend" env DEV_OUTWAY_ROUTES="$state/dev-outway.json" \
            uv run uvicorn grip.dev.dev_outway:create_app --factory --port "$OUTWAY_PORT"
        # The routes other organisations call. With FSC only the inway
        # reaches this port; here the dev outway does.
        # DEV_LINK_SOURCE=head runs the listener from the last commit instead
        # of the working tree, for when the tree is halfway through a change.
        listener_dir="$repo/backend"
        if [ "${DEV_LINK_SOURCE:-tree}" = "head" ]; then
            rm -rf "$state/src" && mkdir -p "$state/src"
            git -C "$repo" archive HEAD backend | tar -x -C "$state/src"
            listener_dir="$state/src/backend"
        fi
        start grip-federation "$listener_dir" env DATABASE_URL="$(grip_db)" DEV_NO_AUTH=1 \
            FEDERATION_INBOUND_ENABLED=1 \
            "$repo/backend/.venv/bin/python" -m uvicorn grip.federation.app:app --port "$GRIP_FEDERATION_PORT"
        "$0" status
        ;;
    peers)
        # Bouwmeester: grip as a peer with role grip, asking on behalf of a
        # unit. The seeded nodes have no unit, so any unit sees them.
        jar="$(mktemp)"; trap 'rm -f "$jar"' EXIT
        curl -sf -c "$jar" -o /dev/null "$BOUWMEESTER_BACKEND/api/auth/status"
        csrf="$(awk '$6 == "bm_csrf" {print $7}' "$jar")"
        unit="$(curl -sf -b "$jar" "$BOUWMEESTER_BACKEND/api/organisatie?format=flat" | python3 -c '
import json, sys
units = json.load(sys.stdin)
units = units if isinstance(units, list) else units.get("items", [])
pick = [u for u in units if u.get("type") == "ministerie"] or units
print(pick[0]["id"])')"
        existing="$(curl -sf -b "$jar" "$BOUWMEESTER_BACKEND/api/admin/federation-peers" | PEER="$GRIP_PEER_ID" python3 -c '
import json, os, sys
print(next((p["id"] for p in json.load(sys.stdin) if p["peer_id"] == os.environ["PEER"]), ""))')"
        # Bouwmeester only accepts an https address for a grip instance; it
        # is shown as the source of an assignment and never called.
        body="{\"naam\":\"DigiGilde (lokale grip)\",\"rol\":\"grip\",\"base_uri\":\"https://grip.digigilde.localhost\",\"opdrachtverkeer_grant_hash\":\"$GRANT_CORPUS_TO_GRIP\""
        if [ -n "$existing" ]; then
            code="$(curl -s -b "$jar" -o /dev/null -w '%{http_code}' -X PATCH -H "X-CSRF-Token: $csrf" -H 'Content-Type: application/json' \
                -d "$body,\"is_active\":true}" "$BOUWMEESTER_BACKEND/api/admin/federation-peers/$existing")"
        else
            code="$(curl -s -b "$jar" -o /dev/null -w '%{http_code}' -X POST -H "X-CSRF-Token: $csrf" -H 'Content-Type: application/json' \
                -d "$body,\"peer_id\":\"$GRIP_PEER_ID\",\"organisatie_eenheid_id\":\"$unit\"}" "$BOUWMEESTER_BACKEND/api/admin/federation-peers")"
        fi
        echo "  Bouwmeester knows grip as peer $GRIP_PEER_ID: HTTP $code"

        # Grip: Bouwmeester as a peer with role corpus for its corpus base
        # URI, next to the stand-in corpora.
        (cd "$repo/backend" && DATABASE_URL="$(grip_db)" DEV_NO_AUTH=1 \
            PEER_ID="$BOUWMEESTER_PEER_ID" BASE="$CORPUS_BASE_URI" GRANT="$GRANT_GRIP_TO_CORPUS" uv run python - <<'PY'
import asyncio, os

from sqlalchemy import select

from grip.core.database import async_session
from grip.federation.models import Peer


async def main() -> None:
    async with async_session() as db:
        peer = (
            await db.execute(select(Peer).where(Peer.peer_id == os.environ["PEER_ID"]))
        ).scalar_one_or_none()
        if peer is None:
            peer = Peer(peer_id=os.environ["PEER_ID"], organisation_tooi_uri="")
            db.add(peer)
        peer.name = "Bouwmeester Voorbeeldministerie (lokaal)"
        peer.organisation_tooi_uri = "https://identifier.overheid.nl/tooi/id/ministerie/mnre1034"
        peer.base_uri = os.environ["BASE"]
        peer.role = "corpus"
        peer.grant_hashes = {"corpus-context": os.environ["GRANT"]}
        peer.is_active = True
        await db.commit()
        print(f"  grip knows Bouwmeester as peer {peer.peer_id} for {peer.base_uri}")


asyncio.run(main())
PY
        )
        ;;
    env)
        echo "DATABASE_URL=$(grip_db)"
        echo "DEV_NO_AUTH=1"
        echo "OUTWAY_URL=http://localhost:$OUTWAY_PORT"
        ;;
    status)
        echo "  dev outway               http://localhost:$OUTWAY_PORT   (unknown grant hashes go on to the stand-in corpus on 8040)"
        echo "  grip federation listener http://localhost:$GRIP_FEDERATION_PORT"
        for name in dev-outway grip-federation; do
            if [ -f "$state/$name.pid" ] && kill -0 "$(cat "$state/$name.pid")" 2>/dev/null; then
                echo "  $name: running"
            else
                echo "  $name: stopped"
            fi
        done
        ;;
    down)
        for name in dev-outway grip-federation; do
            if [ -f "$state/$name.pid" ]; then
                pid="$(cat "$state/$name.pid")"
                pkill -P "$pid" 2>/dev/null || true
                kill "$pid" 2>/dev/null || true
                rm -f "$state/$name.pid"
            fi
        done
        ;;
    *) sed -n '2,14p' "$0"; exit 64 ;;
esac
