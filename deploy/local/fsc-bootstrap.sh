#!/bin/sh
# Make the local grip instances reachable for each other through FSC, only
# between related peers (no full mesh).
#
#   1. each peer registers the service grip-opdrachtverkeer, pointing at its
#      own federation listener behind its own inway
#   2. each peer publishes that service in the directory (a contract with a
#      service publication grant, which the directory signs automatically)
#   3. for each relation, both peers ask for a connection to the other's
#      service (a contract with a service connection grant for its own
#      outway), and the other accepts
#   4. each instance writes the grant hash into its peer registry, through
#      the registry route of grip (with the role of the other peer)
#   5. each registered relation is tested with "Test de verbinding"; the
#      script fails when one of them does not work
#
# The peers that run: a b d (modes fsc, fsc-keycloak, fsc-corpus), or with
# --voorbeeld all seven (local.sh up fsc-voorbeeld): a b d e g o z. A relation
# is only made when both of its peers run.
#
# Idempotent: existing services, contracts and registry rows are reused.
# Needs the stack of `just local-up fsc` (or fsc-voorbeeld) to be running.
set -eu

peers="a b d"
[ "${1:-}" = "--voorbeeld" ] && peers="a b d e g o z"

here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$here/fsc-lib.sh"
service="grip-opdrachtverkeer"

# at peer, other peer, role of the other peer in the registry of "at",
# financial_inspection of the row (only applied when it is created).
relations="
a d counterpart false
a o parent false
a e counterpart true
b d child false
b g counterpart false
b o counterpart false
d a counterpart false
d b parent false
e a counterpart false
e z parent false
g b counterpart false
o b counterpart false
o a child false
z e child false
"

runs() { # peer key
    case " $peers " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

# The relations whose two peers both run, as lines "at other role fi".
active_relations() {
    echo "$relations" | while read -r at other role fi; do
        [ -n "$at" ] || continue
        if runs "$at" && runs "$other"; then echo "$at $other $role $fi"; fi
    done
}

echo "1. services"
for k in $peers; do register_service "$k"; done
echo "2. publications"
for k in $peers; do publish "$k" "$(peer_id_of "$k")"; done
sleep 3
echo "3. connections"
for k in $peers; do api "$k" -o /dev/null -X POST "https://manager-$k:8444/v1/peers/sync" || true; done
active="$(active_relations)"
while read -r at other role fi; do
    connect "$at" "$(peer_id_of "$at")" "$other" "$(peer_id_of "$other")"
done <<EOF
$active
EOF
sleep 3
echo "4. peer registry of grip"
while read -r at other role fi; do
    grant="$(find_grant "$at" GRANT_TYPE_SERVICE_CONNECTION "$(peer_id_of "$other")" "$(peer_id_of "$at")" | cut -d' ' -f1)"
    [ -n "$grant" ] || { echo "no valid connection grant $at -> $other; see the manager logs"; exit 1; }
    registry "$at" "$other" "$grant" "$role" "$fi"
done <<EOF
$active
EOF
echo "5. test the connections"
failed=0
while read -r at other role fi; do
    registry_test "$at" "$other" || failed=1
done <<EOF
$active
EOF
[ "$failed" = 0 ] || { echo "at least one connection test failed"; exit 1; }
echo "done"
