#!/bin/sh
# Shared by the FSC bootstrap scripts: calling the internal APIs of manager
# and controller, making contracts, and writing grip's peer registry.
# Source it; it expects to live next to compose.yml. Set `service` to the
# FSC service the calls are about before using publish, connect or registry.

network="grip-local_default"
group="grip-local"
dir_peer="01700000000000000099"
peer_a="01700000000000000001"
peer_b="01700000000000000002"

# curl inside the compose network, with the admin client certificate of a
# peer. The internal APIs of manager and controller only accept clients
# with a certificate of that peer's internal CA.
api() { # peer key, curl args...
    k="$1"; shift
    docker run --rm --network "$network" -v "$here/state/pki:/pki:ro" curlimages/curl -s \
        --cacert "/pki/internal/$k/ca.pem" \
        --cert "/pki/internal/$k/admin/cert.pem" --key "/pki/internal/$k/admin/key.pem" "$@"
}
psql_grip() { # instance key, sql
    docker compose -p grip-local -f "$here/compose.yml" --profile two exec -T "db-$1" psql -U grip -At -c "$2"
}
json() { python3 -c "$1"; }

now="$(date +%s)"
later="$((now + 365 * 24 * 3600))"
uuid() { python3 -c "import uuid;print(uuid.uuid4())"; }

register_service() { # peer key, endpoint url (default: the peer's grip federation listener)
    k="$1"; endpoint="${2:-http://federation-$1:8090}"
    code="$(api "$k" -o /dev/null -w '%{http_code}' "https://controller-$k:8444/v1/services/$service")"
    if [ "$code" = "200" ]; then echo "  service already registered at peer $k"; return; fi
    code="$(api "$k" -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
        -d "{\"name\":\"$service\",\"endpoint_url\":\"$endpoint\",\"inway_address\":\"https://inway-$k:443\"}" \
        "https://controller-$k:8444/v1/services")"
    echo "  service registered at peer $k: HTTP $code"
}

# The hash of the grant of the given type for the given service provider in
# a contract that is valid (signed by all), or empty.
find_grant() { # peer key, grant type, provider peer id, consumer peer id or ""
    api "$1" "https://manager-$1:8444/v1/contracts?limit=100" | GT="$2" PROV="$3" CONS="$4" SVC="$service" json '
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
        "https://manager-$1:8444/v1/contracts"
}

publish() { # peer key, peer id
    if [ -n "$(find_grant "$1" GRANT_TYPE_SERVICE_PUBLICATION "$2" "")" ]; then
        echo "  publication of peer $1 already valid"; return
    fi
    code="$(create_contract "$1" "{\"type\":\"GRANT_TYPE_SERVICE_PUBLICATION\",\"directory\":{\"peer_id\":\"$dir_peer\"},\"service\":{\"peer_id\":\"$2\",\"name\":\"$service\",\"protocol\":\"PROTOCOL_TCP_HTTP_1.1\"}}")"
    echo "  publication contract of peer $1: HTTP $code"
}

connect() { # consumer key, consumer peer id, provider key, provider peer id
    if [ -n "$(find_grant "$1" GRANT_TYPE_SERVICE_CONNECTION "$4" "$2")" ]; then
        echo "  connection $1 -> $3 already valid"; return
    fi
    thumb="$(api "$1" "https://controller-$1:8444/v1/outways" | json 'import json,sys;print(json.load(sys.stdin)["outways"][0]["public_key_thumbprint"])')"
    code="$(create_contract "$1" "{\"type\":\"GRANT_TYPE_SERVICE_CONNECTION\",\"outway\":{\"peer_id\":\"$2\",\"identification\":{\"type\":\"OUTWAY_IDENTIFICATION_TYPE_PUBLIC_KEY_THUMBPRINT\",\"public_key_thumbprint\":\"$thumb\"}},\"service\":{\"type\":\"SERVICE_TYPE_SERVICE\",\"peer_id\":\"$4\",\"name\":\"$service\"}}")"
    echo "  connection contract $1 -> $3 proposed: HTTP $code"
    # The provider accepts what is waiting for its signature.
    sleep 3
    for hash in $(api "$3" "https://manager-$3:8444/v1/contracts/pending" | json '
import json, sys
for c in json.load(sys.stdin).get("pending_contracts", []):
    print(c["hash"])'); do
        code="$(api "$3" -o /dev/null -w '%{http_code}' -X PUT "https://manager-$3:8444/v1/contracts/$hash/accept")"
        echo "  peer $3 accepted a contract: HTTP $code"
    done
}

registry() { # instance key, other peer id, other name, other base uri, grant hash, role (default counterpart)
    psql_grip "$1" "
        insert into peer (id, peer_id, name, organisation_tooi_uri, base_uri, role, grant_hashes, is_active)
        values (gen_random_uuid(), '$2', '$3', '', '$4', '${6:-counterpart}', '{\"$service\": \"$5\"}'::jsonb, true)
        on conflict (peer_id) do update
            set grant_hashes = peer.grant_hashes || excluded.grant_hashes, base_uri = excluded.base_uri,
                name = excluded.name, is_active = true;" >/dev/null
    echo "  registry of instance $1: peer $2, grant $(printf %s "$5" | cut -c1-24)..."
}

