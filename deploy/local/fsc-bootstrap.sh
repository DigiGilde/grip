#!/bin/sh
# Make the three local grip instances reachable for each other through FSC
# (A <-> B, A <-> D, B <-> D).
#
#   1. each peer registers the service grip-opdrachtverkeer, pointing at its
#      own federation listener behind its own inway
#   2. each peer publishes that service in the directory (a contract with a
#      service publication grant, which the directory signs automatically)
#   3. each peer asks for a connection to the other's service (a contract
#      with a service connection grant for its own outway), and the other
#      accepts
#   4. the grant hashes go into the peer registry of grip
#
# Idempotent: existing services, contracts and registry rows are reused.
# Needs the stack of `just local-up fsc` to be running.
#
#   --voorbeeld   the instances are example instances (local.sh up
#                 fsc-voorbeeld): the registry marks every peer as example
#                 (ADR 0054), or nothing would be exchanged.
set -eu

peer_is_example=false
[ "${1:-}" = "--voorbeeld" ] && peer_is_example=true

here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$here/fsc-lib.sh"
service="grip-opdrachtverkeer"

echo "1. services"
register_service a
register_service b
register_service d
echo "2. publications"
publish a "$peer_a"
publish b "$peer_b"
publish d "$peer_d"
sleep 3
echo "3. connections"
api a -o /dev/null -X POST "https://manager-a:8444/v1/peers/sync" || true
api b -o /dev/null -X POST "https://manager-b:8444/v1/peers/sync" || true
api d -o /dev/null -X POST "https://manager-d:8444/v1/peers/sync" || true
connect b "$peer_b" a "$peer_a"
connect a "$peer_a" b "$peer_b"
connect d "$peer_d" a "$peer_a"
connect a "$peer_a" d "$peer_d"
connect d "$peer_d" b "$peer_b"
connect b "$peer_b" d "$peer_d"
sleep 3
echo "4. peer registry of grip"
grant_b_to_a="$(find_grant b GRANT_TYPE_SERVICE_CONNECTION "$peer_a" "$peer_b" | cut -d' ' -f1)"
grant_a_to_b="$(find_grant a GRANT_TYPE_SERVICE_CONNECTION "$peer_b" "$peer_a" | cut -d' ' -f1)"
[ -n "$grant_b_to_a" ] && [ -n "$grant_a_to_b" ] || { echo "no valid connection grant found; see the manager logs"; exit 1; }
registry b "$peer_a" "DigiGilde voorbeeld" "http://localhost:9001" "$grant_b_to_a"
registry a "$peer_b" "Voorbeeldministerie" "http://localhost:9002" "$grant_a_to_b"
for pair in "d $peer_d a $peer_a" "a $peer_a d $peer_d" "d $peer_d b $peer_b" "b $peer_b d $peer_d"; do
    set -- $pair
    grant="$(find_grant "$1" GRANT_TYPE_SERVICE_CONNECTION "$4" "$2" | cut -d' ' -f1)"
    [ -n "$grant" ] || { echo "no valid connection grant $1 -> $3; see the manager logs"; exit 1; }
    case "$3" in
        a) name="DigiGilde voorbeeld"; uri="http://localhost:9001" ;;
        b) name="Voorbeeldministerie"; uri="http://localhost:9002" ;;
        d) name="Voorbeeldprogramma"; uri="http://localhost:9003" ;;
    esac
    registry "$1" "$4" "$name" "$uri" "$grant"
done
echo "done"
