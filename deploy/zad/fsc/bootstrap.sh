#!/bin/sh
# Make the three example instances reachable for each other through FSC on ZAD
# (A <-> B, A <-> D, B <-> D), in the group grip-voorbeeld.
#
#   1. each peer registers the service grip-opdrachtverkeer, pointing at the
#      federation listener of its own instance behind its own inway
#   2. each peer publishes that service in the directory (a contract with a
#      service publication grant, which the directory signs automatically)
#   3. each peer asks for a connection to the service of each other peer (a
#      contract with a service connection grant for its own outway), and the
#      other accepts
#   4. the grant hashes go to $OUT/registry-<k>.sql, one file per instance, and
#      to a table for entering by hand under Beheer > Koppelingen
#
# Idempotent: existing services and valid contracts are reused, and the SQL
# can be run again.
#
# Needs: BASE_DOMAIN, DEPLOYMENT, PROJECT_A, PROJECT_B, PROJECT_D, and PKI_DIR
# from pki.sh. The internal APIs of the managers (port 8444) and controllers
# (port 8444) must be reachable from where this runs; override the addresses
# with MANAGER_URL_<A|B|D> and CONTROLLER_URL_<A|B|D>, the inway address with
# INWAY_ADDRESS_<K> and the service endpoint with ENDPOINT_URL_<K>.
#
# --dry-run prints the calls and executes none.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
PKI_DIR="${PKI_DIR:-$here/state/pki}"
OUT="${OUT:-$here/state/bootstrap}"
dry_run=0
[ "${1:-}" = "--dry-run" ] && dry_run=1

for var in BASE_DOMAIN DEPLOYMENT PROJECT_A PROJECT_B PROJECT_D; do
    eval "[ -n \"\${$var:-}\" ]" || { echo "$var is not set" >&2; exit 1; }
done

service="grip-opdrachtverkeer"
group="grip-voorbeeld"
dir_peer="01800000000000000099"

peer_id_of() { case "$1" in a) echo 01800000000000000001 ;; b) echo 01800000000000000002 ;; d) echo 01800000000000000004 ;; esac; }
name_of() { case "$1" in a) echo "DigiGilde voorbeeld" ;; b) echo "Voorbeeldministerie" ;; d) echo "Voorbeeldprogramma" ;; esac; }
tooi_of() {
    case "$1" in
        a) echo "https://identifier.overheid.nl/tooi/id/oorg/oorg99002" ;;
        b | d) echo "https://identifier.overheid.nl/tooi/id/ministerie/mnre9001" ;;
    esac
}
project_of() { case "$1" in a) echo "$PROJECT_A" ;; b) echo "$PROJECT_B" ;; d) echo "$PROJECT_D" ;; esac; }
host_of() { printf '%s-%s-%s.%s' "$1" "$DEPLOYMENT" "$(project_of "$2")" "$BASE_DOMAIN"; }
base_uri_of() { echo "https://$(host_of component-1 "$1")"; }

# An address from the environment, or the default derived from the ZAD host name.
setting() { # variable name prefix, key, default
    upper="$(printf %s "$2" | tr '[:lower:]' '[:upper:]')"
    eval "value=\${$1_$upper:-}"
    echo "${value:-$3}"
}
manager_url() { setting MANAGER_URL "$1" "https://$(host_of manager "$1"):8444"; }
controller_url() { setting CONTROLLER_URL "$1" "https://$(host_of controller "$1"):8444"; }
inway_address() { setting INWAY_ADDRESS "$1" "https://$(host_of inway "$1"):443"; }
endpoint_url() { setting ENDPOINT_URL "$1" "http://$DEPLOYMENT-federation:8090"; }

# curl with the admin client certificate of a peer. The internal APIs only
# accept clients with a certificate of that peer's internal CA.
api() { # peer key, curl args...
    k="$1"; shift
    if [ "$dry_run" = 1 ]; then
        echo "  curl $*" >&2
        return 0
    fi
    curl -sS --cacert "$PKI_DIR/peers/$k/internal/ca.pem" \
        --cert "$PKI_DIR/peers/$k/internal/admin/cert.pem" \
        --key "$PKI_DIR/peers/$k/internal/admin/key.pem" "$@"
}
json() { uv run --no-project python3 -c "$1"; }

now="$(date +%s)"
later="$((now + 365 * 24 * 3600))"
uuid() { uv run --no-project python3 -c "import uuid;print(uuid.uuid4())"; }

register_service() { # peer key
    k="$1"; url="$(controller_url "$k")"
    code="$(api "$k" -o /dev/null -w '%{http_code}' "$url/v1/services/$service")"
    if [ "$code" = "200" ]; then echo "  service already registered at peer $k"; return; fi
    code="$(api "$k" -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
        -d "{\"name\":\"$service\",\"endpoint_url\":\"$(endpoint_url "$k")\",\"inway_address\":\"$(inway_address "$k")\"}" \
        "$url/v1/services")"
    echo "  service registered at peer $k: HTTP $code"
}

# The hash of the grant of the given type for the given service provider in a
# contract that is valid (signed by all), or empty.
find_grant() { # peer key, grant type, provider peer id, consumer peer id or ""
    [ "$dry_run" = 1 ] && return 0
    api "$1" "$(manager_url "$1")/v1/contracts?limit=100" | GT="$2" PROV="$3" CONS="$4" SVC="$service" json '
import json, os, sys
data = json.load(sys.stdin)
for c in data.get("contracts", []):
    if c.get("state") not in (None, "CONTRACT_STATE_VALID"):
        continue
    for g in c["content"]["grants"]:
        if g["type"] != os.environ["GT"]:
            continue
        s = g["service"]
        if s.get("peer_id") != os.environ["PROV"] or s.get("name") != os.environ["SVC"]:
            continue
        if os.environ["CONS"] and g.get("outway", {}).get("peer_id") != os.environ["CONS"]:
            continue
        print(g["hash"], c["hash"])
        sys.exit(0)
'
}

create_contract() { # peer key, grant json -> prints HTTP code
    api "$1" -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
        -d "{\"contract_content\":{\"iv\":\"$(uuid)\",\"group_id\":\"$group\",\"validity\":{\"not_before\":$now,\"not_after\":$later},\"grants\":[$2],\"hash_algorithm\":\"HASH_ALGORITHM_SHA3_512\",\"created_at\":$now}}" \
        "$(manager_url "$1")/v1/contracts"
}

publish() { # peer key
    id="$(peer_id_of "$1")"
    if [ -n "$(find_grant "$1" GRANT_TYPE_SERVICE_PUBLICATION "$id" "")" ]; then
        echo "  publication of peer $1 already valid"; return
    fi
    code="$(create_contract "$1" "{\"type\":\"GRANT_TYPE_SERVICE_PUBLICATION\",\"directory\":{\"peer_id\":\"$dir_peer\"},\"service\":{\"peer_id\":\"$id\",\"name\":\"$service\",\"protocol\":\"PROTOCOL_TCP_HTTP_1.1\"}}")"
    echo "  publication contract of peer $1: HTTP $code"
}

connect() { # consumer key, provider key
    cid="$(peer_id_of "$1")"; pid="$(peer_id_of "$2")"
    if [ -n "$(find_grant "$1" GRANT_TYPE_SERVICE_CONNECTION "$pid" "$cid")" ]; then
        echo "  connection $1 -> $2 already valid"; return
    fi
    if [ "$dry_run" = 1 ]; then
        thumb="<public key thumbprint of outway $1>"
        api "$1" "$(controller_url "$1")/v1/outways"
    else
        thumb="$(api "$1" "$(controller_url "$1")/v1/outways" | json 'import json,sys;print(json.load(sys.stdin)["outways"][0]["public_key_thumbprint"])')"
    fi
    code="$(create_contract "$1" "{\"type\":\"GRANT_TYPE_SERVICE_CONNECTION\",\"outway\":{\"peer_id\":\"$cid\",\"identification\":{\"type\":\"OUTWAY_IDENTIFICATION_TYPE_PUBLIC_KEY_THUMBPRINT\",\"public_key_thumbprint\":\"$thumb\"}},\"service\":{\"type\":\"SERVICE_TYPE_SERVICE\",\"peer_id\":\"$pid\",\"name\":\"$service\"}}")"
    echo "  connection contract $1 -> $2 proposed: HTTP $code"
    # The provider accepts what is waiting for its signature.
    [ "$dry_run" = 1 ] || sleep 3
    if [ "$dry_run" = 1 ]; then
        api "$2" "$(manager_url "$2")/v1/contracts/pending"
        api "$2" -X PUT "$(manager_url "$2")/v1/contracts/<hash>/accept"
        return
    fi
    for hash in $(api "$2" "$(manager_url "$2")/v1/contracts/pending" | json '
import json, sys
for c in json.load(sys.stdin).get("pending_contracts", []):
    print(c["hash"])'); do
        code="$(api "$2" -o /dev/null -w '%{http_code}' -X PUT "$(manager_url "$2")/v1/contracts/$hash/accept")"
        echo "  peer $2 accepted a contract: HTTP $code"
    done
}

sql_quote() { printf %s "$1" | sed "s/'/''/g"; }

# One row for the peer registry of instance $1: the counterpart $2.
registry_row() { # instance key, counterpart key, grant hash
    printf "insert into peer (id, peer_id, name, organisation_tooi_uri, base_uri, role, grant_hashes, is_active, is_example)\n"
    printf "values (gen_random_uuid(), '%s', '%s', '%s', '%s', 'counterpart', '{\"%s\": \"%s\"}'::jsonb, true, true)\n" \
        "$(peer_id_of "$2")" "$(sql_quote "$(name_of "$2")")" "$(tooi_of "$2")" "$(base_uri_of "$2")" "$service" "$3"
    printf "on conflict (peer_id) do update\n"
    printf "    set grant_hashes = peer.grant_hashes || excluded.grant_hashes, base_uri = excluded.base_uri,\n"
    printf "        name = excluded.name, organisation_tooi_uri = excluded.organisation_tooi_uri,\n"
    printf "        is_active = true, is_example = true;\n"
}

echo "1. services"
for k in a b d; do register_service "$k"; done
echo "2. publications"
for k in a b d; do publish "$k"; done
[ "$dry_run" = 1 ] || sleep 3
echo "3. connections"
for k in a b d; do api "$k" -o /dev/null -X POST "$(manager_url "$k")/v1/peers/sync" || true; done
for pair in "b a" "a b" "d a" "a d" "d b" "b d"; do
    set -- $pair
    connect "$1" "$2"
done
[ "$dry_run" = 1 ] || sleep 3

echo "4. peer registry of grip"
if [ "$dry_run" = 1 ]; then
    echo "  would write $OUT/registry-<k>.sql with the grant hashes found"
    exit 0
fi
mkdir -p "$OUT"
table="$OUT/registry.txt"
printf 'instance\tpeer id\tname\torganisation TOOI URI\tbase URI\trole\tgrant hash (%s)\tis_example\n' "$service" > "$table"
for k in a b d; do
    sql="$OUT/registry-$k.sql"
    printf -- '-- Peer registry of instance %s (%s)\n' "$k" "$(name_of "$k")" > "$sql"
    for o in a b d; do
        [ "$o" = "$k" ] && continue
        grant="$(find_grant "$k" GRANT_TYPE_SERVICE_CONNECTION "$(peer_id_of "$o")" "$(peer_id_of "$k")" | cut -d' ' -f1)"
        [ -n "$grant" ] || { echo "no valid connection grant $k -> $o; see the manager logs" >&2; exit 1; }
        registry_row "$k" "$o" "$grant" >> "$sql"
        printf '%s\t%s\t%s\t%s\t%s\tcounterpart\t%s\ttrue\n' \
            "$k" "$(peer_id_of "$o")" "$(name_of "$o")" "$(tooi_of "$o")" "$(base_uri_of "$o")" "$grant" >> "$table"
    done
    echo "  wrote $sql"
done
echo
echo "Without database access, enter these under Beheer > Koppelingen of each instance:"
cat "$table"
echo "done"
