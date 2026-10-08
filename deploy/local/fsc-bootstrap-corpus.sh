#!/bin/sh
# Add the local Bouwmeester to the FSC group as a corpus system (peer C).
#
#   1. peer C registers and publishes the service corpus-context, pointing
#      at Bouwmeester's corpus-context application on the host
#   2. the grip instances get a connection to corpus-context, and peer C
#      gets a connection to grip-opdrachtverkeer of each grip instance
#   3. grip's peer registry learns the corpus (role corpus, by its base URI)
#   4. Bouwmeester's peer table learns the grip instances, with the grant
#      hash of its connection to each
#
# Needs: `just local-up fsc-corpus`, `just local-fsc-init`, and Bouwmeester
# running (`just bouwmeester-up`). Idempotent.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$here/fsc-lib.sh"

peer_c="01700000000000000003"
corpus_base="https://corpus.voorbeeldministerie.localhost"
bouwmeester="http://localhost:9210"
corpus_endpoint="http://host.docker.internal:9211"

echo "1. corpus-context at peer C"
service="corpus-context"
register_service c "$corpus_endpoint"
publish c "$peer_c"
sleep 3
for k in a b c; do api "$k" -o /dev/null -X POST "https://manager-$k:8444/v1/peers/sync" || true; done

echo "2. connections"
connect a "$peer_a" c "$peer_c"
connect b "$peer_b" c "$peer_c"
service="grip-opdrachtverkeer"
connect c "$peer_c" a "$peer_a"
connect c "$peer_c" b "$peer_b"
sleep 3

echo "3. peer registry of grip"
service="corpus-context"
for pair in "a $peer_a" "b $peer_b"; do
    set -- $pair
    grant="$(find_grant "$1" GRANT_TYPE_SERVICE_CONNECTION "$peer_c" "$2" | cut -d' ' -f1)"
    [ -n "$grant" ] || { echo "no valid grant for $1 -> corpus-context"; exit 1; }
    registry "$1" "$peer_c" "Corpus Voorbeeldministerie (lokaal)" "$corpus_base" "$grant" corpus
done

echo "4. peer table of Bouwmeester"
service="grip-opdrachtverkeer"
jar="$(mktemp)"; trap 'rm -f "$jar"' EXIT
curl -sf -c "$jar" -o /dev/null "$bouwmeester/api/auth/status"
csrf="$(awk '$6 == "bm_csrf" {print $7}' "$jar")"
unit="$(curl -sf -b "$jar" "$bouwmeester/api/organisatie?format=flat" | python3 -c '
import json, sys
units = json.load(sys.stdin)
pick = [u for u in units if u.get("type") == "ministerie"] or units
print(pick[0]["id"])')"
routes=""
for triple in "a $peer_a DigiGilde-voorbeeld-(FSC) https://grip-a.fsc.localhost" "b $peer_b Voorbeeldministerie-(FSC) https://grip-b.fsc.localhost"; do
    set -- $triple
    name="$(printf %s "$3" | tr '-' ' ')"
    grant="$(find_grant c GRANT_TYPE_SERVICE_CONNECTION "$2" "$peer_c" | cut -d' ' -f1)"
    [ -n "$grant" ] || { echo "no valid grant for corpus -> grip $1"; exit 1; }
    existing="$(curl -sf -b "$jar" "$bouwmeester/api/admin/federation-peers" | PEER="$2" python3 -c '
import json, os, sys
print(next((p["id"] for p in json.load(sys.stdin) if p["peer_id"] == os.environ["PEER"]), ""))')"
    body="\"naam\":\"$name\",\"rol\":\"grip\",\"base_uri\":\"$4\",\"opdrachtverkeer_grant_hash\":\"$grant\""
    if [ -n "$existing" ]; then
        code="$(curl -s -b "$jar" -o /dev/null -w '%{http_code}' -X PATCH -H "X-CSRF-Token: $csrf" -H 'Content-Type: application/json' \
            -d "{$body,\"is_active\":true}" "$bouwmeester/api/admin/federation-peers/$existing")"
    else
        code="$(curl -s -b "$jar" -o /dev/null -w '%{http_code}' -X POST -H "X-CSRF-Token: $csrf" -H 'Content-Type: application/json' \
            -d "{$body,\"peer_id\":\"$2\",\"organisatie_eenheid_id\":\"$unit\"}" "$bouwmeester/api/admin/federation-peers")"
    fi
    echo "  Bouwmeester knows grip $1 as peer $2: HTTP $code"
    routes="$routes\"$grant\": {\"target\": \"http://localhost:9240\", \"note\": \"Bouwmeester -> grip $1, through the real outway of peer C\"},"
done

# Bouwmeester has one outway address. When that is the dev outway, these
# routes pass the FSC grant hashes on to the real outway of peer C, so one
# Bouwmeester can show the grip you develop on and the grips behind FSC.
mkdir -p "$here/state/dev-link"
printf '{%s}\n' "${routes%,}" > "$here/state/dev-link/fsc-routes.json"
echo "  routes for the dev outway written (./dev-link.sh up picks them up)"
echo "done"
