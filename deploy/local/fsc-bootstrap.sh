#!/bin/sh
# Make the two local grip instances reachable for each other through FSC.
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
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$here/fsc-lib.sh"
service="grip-opdrachtverkeer"

echo "1. services"
register_service a
register_service b
echo "2. publications"
publish a "$peer_a"
publish b "$peer_b"
sleep 3
echo "3. connections"
api a -o /dev/null -X POST "https://manager-a:8444/v1/peers/sync" || true
api b -o /dev/null -X POST "https://manager-b:8444/v1/peers/sync" || true
connect b "$peer_b" a "$peer_a"
connect a "$peer_a" b "$peer_b"
sleep 3
echo "4. peer registry of grip"
grant_b_to_a="$(find_grant b GRANT_TYPE_SERVICE_CONNECTION "$peer_a" "$peer_b" | cut -d' ' -f1)"
grant_a_to_b="$(find_grant a GRANT_TYPE_SERVICE_CONNECTION "$peer_b" "$peer_a" | cut -d' ' -f1)"
[ -n "$grant_b_to_a" ] && [ -n "$grant_a_to_b" ] || { echo "no valid connection grant found; see the manager logs"; exit 1; }
registry b "$peer_a" "DigiGilde voorbeeld" "http://localhost:9001" "$grant_b_to_a"
registry a "$peer_b" "Voorbeeldministerie" "http://localhost:9002" "$grant_a_to_b"
echo "done"
