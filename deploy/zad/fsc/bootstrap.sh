#!/bin/sh
# The bootstrap of one peer of the example FSC group "grip-voorbeeld" on ZAD.
# It runs in the deployment of that peer, as the component fscboot-<k> (image
# fsc-bootstrap): only from there are the internal APIs of its manager and
# controller (port 8444) reachable. Each peer does its own side:
#
#   1. register the service grip-opdrachtverkeer at its own controller,
#      pointing at the federation listener of its instance behind its inway
#   2. publish that service in the directory (a contract with a service
#      publication grant, which the directory signs automatically)
#   3. ask for a connection to the service of each other peer in PEERS (a
#      contract with a service connection grant for its own outway); the
#      managers of this closed group sign such a contract when it arrives
#      (AUTO_SIGN_GRANTS=serviceConnection)
#   4. send again what OpenFSC gave up delivering to another peer
#   5. once every connection is valid: print the other peers for the peer
#      registry of grip, with their grant hashes, as a table and as SQL
#
# Idempotent: existing services and contracts are reused.
#
# Needs: PEER (a, b or d), PEERS (the peers of the group, default "a b d"),
# BASE_DOMAIN, PROJECT and DEPLOYMENT_<K> for every peer in PEERS. The internal
# APIs default to the platform's service names in the own deployment
# (https://<deployment>-manager:8444 and https://<deployment>-controller:8444);
# override them with MANAGER_URL and CONTROLLER_URL, the inway address with
# INWAY_ADDRESS and the service endpoint with ENDPOINT_URL. TLS_ROOT_CERT,
# TLS_CERT and TLS_KEY are the internal CA and the admin client certificate
# of the peer (default: from PKI_DIR, the output of pki.sh).
#
# A round exits 0 when every connection is valid, 3 while it waits for
# another peer or the directory, and otherwise on an error.
#   --loop     the entrypoint of the image: a round every BOOTSTRAP_INTERVAL
#              seconds (default 30), slowing down to ten times that while
#              nothing moves, and once done every BOOTSTRAP_RECHECK seconds
#              (default 3600). Before the first success, BOOTSTRAP_MAX_FAILURES
#              errors in a row (default 10) stop it, so the platform shows it.
#   --dry-run  print the calls of one round and execute none
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
PKI_DIR="${PKI_DIR:-$here/state/pki}"

mode=once
case "${1:-}" in
    "") ;;
    --loop) mode=loop ;;
    --dry-run) mode=dry ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
esac

PEER="${PEER:-}"
PEERS="${PEERS:-a b d}"
for var in PEER BASE_DOMAIN PROJECT; do
    eval "[ -n \"\${$var:-}\" ]" || { echo "$var is not set" >&2; exit 2; }
done
case " $PEERS " in
    *" $PEER "*) ;;
    *) echo "PEER $PEER is not one of PEERS ($PEERS)" >&2; exit 2 ;;
esac
for k in $PEERS; do
    case "$k" in
        a | b | d) ;;
        *) echo "unknown peer in PEERS: $k" >&2; exit 2 ;;
    esac
    var="DEPLOYMENT_$(printf %s "$k" | tr '[:lower:]' '[:upper:]')"
    eval "[ -n \"\${$var:-}\" ]" || { echo "$var is not set" >&2; exit 2; }
done

if [ "$mode" = loop ]; then
    interval="${BOOTSTRAP_INTERVAL:-30}"
    recheck="${BOOTSTRAP_RECHECK:-3600}"
    max_failures="${BOOTSTRAP_MAX_FAILURES:-10}"
    for n in "$interval" "$recheck" "$max_failures"; do
        case "$n" in
            "" | 0 | *[!0-9]*) echo "BOOTSTRAP_INTERVAL, BOOTSTRAP_RECHECK and BOOTSTRAP_MAX_FAILURES are whole numbers above 0" >&2; exit 2 ;;
        esac
    done
    # As process 1 of the container the shell ignores TERM without a trap,
    # and a stop would wait out the whole grace period.
    trap 'exit 0' TERM INT
    done_once=0
    failures=0
    streak=0
    while :; do
        rc=0
        sh "$0" || rc=$?
        if [ "$rc" = 0 ]; then
            done_once=1
            failures=0
            streak=0
            pause="$recheck"
        else
            if [ "$rc" = 3 ]; then
                failures=0
            else
                failures=$((failures + 1))
                if [ "$done_once" = 0 ] && [ "$failures" -ge "$max_failures" ]; then
                    echo "bootstrap: $failures rounds in a row failed; stopping" >&2
                    exit 1
                fi
            fi
            streak=$((streak + 1))
            pause="$interval"
            i=1
            while [ "$i" -lt "$streak" ] && [ "$pause" -lt "$((interval * 10))" ]; do
                pause=$((pause * 2))
                i=$((i + 1))
            done
            [ "$pause" -le "$((interval * 10))" ] || pause=$((interval * 10))
        fi
        echo "bootstrap: next round in $pause seconds"
        # In the background, so a TERM is handled during the pause.
        sleep "$pause" &
        wait $!
    done
fi

service="grip-opdrachtverkeer"
group="grip-voorbeeld"
dir_peer="01800000000000000099"

peer_id_of() { case "$1" in a) echo 01800000000000000001 ;; b) echo 01800000000000000002 ;; d) echo 01800000000000000004 ;; esac; }
name_of() { case "$1" in a) echo "DigiGilde voorbeeld" ;; b) echo "Ministerie van BZK voorbeeld" ;; d) echo "MOZa voorbeeld" ;; esac; }
tooi_of() {
    case "$1" in
        a) echo "https://identifier.overheid.nl/tooi/id/oorg/oorg99002" ;;
        b | d) echo "https://identifier.overheid.nl/tooi/id/ministerie/mnre9001" ;;
    esac
}
deployment_of() { case "$1" in a) echo "$DEPLOYMENT_A" ;; b) echo "$DEPLOYMENT_B" ;; d) echo "$DEPLOYMENT_D" ;; esac; }
host_of() { printf '%s-%s-%s.%s' "$1" "$(deployment_of "$2")" "$PROJECT" "$BASE_DOMAIN"; }
base_uri_of() { echo "https://$(host_of component-1 "$1")"; }

self_id="$(peer_id_of "$PEER")"
deployment="$(deployment_of "$PEER")"
manager="${MANAGER_URL:-https://$deployment-manager:8444}"
controller="${CONTROLLER_URL:-https://$deployment-controller:8444}"
inway="${INWAY_ADDRESS:-https://$(host_of inway "$PEER"):443}"
endpoint="${ENDPOINT_URL:-http://$deployment-federation:8090}"
ca="${TLS_ROOT_CERT:-$PKI_DIR/peers/$PEER/internal/ca.pem}"
cert="${TLS_CERT:-$PKI_DIR/peers/$PEER/internal/admin/cert.pem}"
key="${TLS_KEY:-$PKI_DIR/peers/$PEER/internal/admin/key.pem}"

# curl with the admin client certificate of the peer. The internal APIs only
# accept clients with a certificate of that peer's internal CA.
api() {
    if [ "$mode" = dry ]; then
        echo "  curl $*" >&2
        return 0
    fi
    curl -sS --max-time 30 --cacert "$ca" --cert "$cert" --key "$key" "$@"
}

# The body of an answer, or an error when it is not a success.
get() { api --fail "$1"; }

# A change; anything but a success stops the round.
call() { # what, method, url, JSON body (optional)
    if [ "$#" -ge 4 ]; then
        code="$(api -o /dev/null -w '%{http_code}' -X "$2" -H 'Content-Type: application/json' -d "$4" "$3")"
    else
        code="$(api -o /dev/null -w '%{http_code}' -X "$2" "$3")"
    fi
    if [ "$mode" = dry ]; then
        echo "  $1"
        return 0
    fi
    case "$code" in
        2??) echo "  $1: HTTP $code" ;;
        *) echo "  $1 failed: HTTP $code" >&2; exit 1 ;;
    esac
}

uuid() {
    if [ -r /proc/sys/kernel/random/uuid ]; then
        cat /proc/sys/kernel/random/uuid
    else
        uuidgen | tr '[:upper:]' '[:lower:]'
    fi
}

# The grant goes in through a variable: bash 3.2, the sh of macOS, splits a
# JSON object written out inside "$(...)".
propose() { # what, grant JSON
    now="$(date +%s)"
    body="$(printf '{"contract_content":{"iv":"%s","group_id":"%s","validity":{"not_before":%s,"not_after":%s},"grants":[%s],"hash_algorithm":"HASH_ALGORITHM_SHA3_512","created_at":%s}}' \
        "$(uuid)" "$group" "$now" "$((now + 365 * 24 * 3600))" "$2" "$now")"
    call "$1" POST "$manager/v1/contracts" "$body"
}

# "<grant hash> <contract hash>" of the first grant of this type for the
# service of the provider (and the outway of the consumer) in a contract in
# this state, or nothing.
grant() { # grant type, provider peer id, consumer peer id or "", contract state
    printf '%s' "$contracts" | jq -r --arg type "$1" --arg provider "$2" --arg consumer "$3" \
        --arg state "$4" --arg service "$service" '
        first(.contracts[] | select((.state // "CONTRACT_STATE_VALID") == $state) | .hash as $contract
            | .content.grants[]
            | select(.type == $type and .service.peer_id == $provider and .service.name == $service)
            | select($consumer == "" or .outway.peer_id == $consumer)
            | "\(.hash) \($contract)")'
}

# OpenFSC retries a delivery to another peer a few times and then gives up; a
# delivery without a next attempt is sent again.
resend() { # contract hash
    case "$1" in
        "" | . | .. | *[!A-Za-z0-9._~\$+-]*) echo "  skipped a contract hash of an unexpected form" >&2; return 0 ;;
    esac
    deliveries="$(get "$manager/v1/contracts/$1/distributions")"
    [ "$mode" != dry ] || return 0
    printf '%s' "$deliveries" | jq -r '.distributions[]? | select((.nextAttemptAt // 0) == 0) | "\(.peer_id) \(.action)"' |
        while read -r to action; do
            call "sent again to peer $to ($action)" PUT "$manager/v1/contracts/$1/distributions/$to/$action/retry"
        done
}

waiting=0
echo "peer $PEER ($(name_of "$PEER")) in deployment $deployment"

echo "1. service $service"
code="$(api -o /dev/null -w '%{http_code}' "$controller/v1/services/$service")"
if [ "$code" = 200 ]; then
    echo "  registered"
else
    call "registered at the controller" POST "$controller/v1/services" \
        "{\"name\":\"$service\",\"endpoint_url\":\"$endpoint\",\"inway_address\":\"$inway\"}"
fi

contracts="$(get "$manager/v1/contracts?limit=100")"
[ "$mode" != dry ] || contracts='{"contracts":[]}'
printf '%s' "$contracts" | jq -e '.contracts | type == "array"' >/dev/null ||
    { echo "the manager answered without a list of contracts" >&2; exit 1; }

echo "2. publication in the directory"
if [ -n "$(grant GRANT_TYPE_SERVICE_PUBLICATION "$self_id" "" CONTRACT_STATE_VALID)" ]; then
    echo "  valid"
elif [ -n "$(grant GRANT_TYPE_SERVICE_PUBLICATION "$self_id" "" CONTRACT_STATE_PROPOSED)" ]; then
    echo "  waiting for the directory"
    waiting=1
else
    publication="{\"type\":\"GRANT_TYPE_SERVICE_PUBLICATION\",\"directory\":{\"peer_id\":\"$dir_peer\"},\"service\":{\"peer_id\":\"$self_id\",\"name\":\"$service\",\"protocol\":\"PROTOCOL_TCP_HTTP_1.1\"}}"
    propose "proposed" "$publication"
    waiting=1
fi

echo "3. connections"
api -o /dev/null -X POST "$manager/v1/peers/sync" || echo "  the peer sync failed; going on" >&2
for o in $PEERS; do
    [ "$o" = "$PEER" ] && continue
    pid="$(peer_id_of "$o")"
    if [ -n "$(grant GRANT_TYPE_SERVICE_CONNECTION "$pid" "$self_id" CONTRACT_STATE_VALID)" ]; then
        echo "  to peer $o: valid"
        continue
    fi
    waiting=1
    if [ -n "$(grant GRANT_TYPE_SERVICE_CONNECTION "$pid" "$self_id" CONTRACT_STATE_PROPOSED)" ]; then
        echo "  to peer $o: waiting for its signature"
        continue
    fi
    listing="$(get "$manager/v1/peers/$dir_peer/services?peer_id=$pid")"
    if [ "$mode" != dry ] &&
        [ "$(printf '%s' "$listing" | jq --arg service "$service" '[.services[]? | select(.name == $service)] | length')" = 0 ]; then
        echo "  to peer $o: its service is not in the directory yet"
        continue
    fi
    outways="$(get "$controller/v1/outways")"
    if [ "$mode" = dry ]; then
        thumb="<public key thumbprint of the outway of peer $PEER>"
    else
        thumb="$(printf '%s' "$outways" | jq -r '.outways[0].public_key_thumbprint // empty')"
    fi
    if [ -z "$thumb" ]; then
        echo "  to peer $o: the outway has not registered at the controller yet"
        continue
    fi
    connection="{\"type\":\"GRANT_TYPE_SERVICE_CONNECTION\",\"outway\":{\"peer_id\":\"$self_id\",\"identification\":{\"type\":\"OUTWAY_IDENTIFICATION_TYPE_PUBLIC_KEY_THUMBPRINT\",\"public_key_thumbprint\":\"$thumb\"}},\"service\":{\"type\":\"SERVICE_TYPE_SERVICE\",\"peer_id\":\"$pid\",\"name\":\"$service\"}}"
    propose "to peer $o: proposed" "$connection"
done

echo "4. deliveries"
for hash in $(printf '%s' "$contracts" | jq -r --arg service "$service" '.contracts[]
    | select((.state // "CONTRACT_STATE_VALID") == "CONTRACT_STATE_VALID" or .state == "CONTRACT_STATE_PROPOSED")
    | select(any(.content.grants[]; .service.name == $service)) | .hash'); do
    resend "$hash"
done

if [ "$mode" = dry ]; then
    echo "5. would print the peer registry once every connection is valid"
    exit 0
fi
if [ "$waiting" = 1 ]; then
    echo "not done yet"
    exit 3
fi

sql_quote() { printf %s "$1" | sed "s/'/''/g"; }

echo "5. peer registry of grip in $(name_of "$PEER"): enter under Beheer > Koppelingen"
printf 'peer id\tname\torganisation TOOI URI\tbase URI\trole\tgrant hash (%s)\texample\n' "$service"
for o in $PEERS; do
    [ "$o" = "$PEER" ] && continue
    hash="$(grant GRANT_TYPE_SERVICE_CONNECTION "$(peer_id_of "$o")" "$self_id" CONTRACT_STATE_VALID | cut -d' ' -f1)"
    printf '%s\t%s\t%s\t%s\tcounterpart\t%s\ttrue\n' \
        "$(peer_id_of "$o")" "$(name_of "$o")" "$(tooi_of "$o")" "$(base_uri_of "$o")" "$hash"
done
echo "The same for the database console:"
for o in $PEERS; do
    [ "$o" = "$PEER" ] && continue
    hash="$(grant GRANT_TYPE_SERVICE_CONNECTION "$(peer_id_of "$o")" "$self_id" CONTRACT_STATE_VALID | cut -d' ' -f1)"
    printf "insert into peer (id, peer_id, name, organisation_tooi_uri, base_uri, role, grant_hashes, is_active, is_example)\n"
    printf "values (gen_random_uuid(), '%s', '%s', '%s', '%s', 'counterpart', '{\"%s\": \"%s\"}'::jsonb, true, true)\n" \
        "$(peer_id_of "$o")" "$(sql_quote "$(name_of "$o")")" "$(tooi_of "$o")" "$(base_uri_of "$o")" "$service" "$hash"
    printf "on conflict (peer_id) do update\n"
    printf "    set grant_hashes = peer.grant_hashes || excluded.grant_hashes, base_uri = excluded.base_uri,\n"
    printf "        name = excluded.name, organisation_tooi_uri = excluded.organisation_tooi_uri,\n"
    printf "        is_active = true, is_example = true;\n"
done
echo "done"
