#!/bin/sh
# Certificates for a private FSC group on this machine. Nothing here is
# PKIoverheid; the group exists only inside the local compose network.
#
# Two kinds of trust, as FSC prescribes:
#   group     one CA shared by all peers. A certificate carries the peer id
#             in the subject serialNumber and the organisation name in O.
#   internal  one CA per peer, for the traffic between its own components.
#
# Output in ./state/pki (gitignored). Existing files are kept; pass --fresh
# to start over (the FSC databases must then be emptied as well).
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
pki="$here/state/pki"
[ "${1:-}" = "--fresh" ] && rm -rf "$pki"
mkdir -p "$pki"

DAYS=825

# The inway refuses a caller whose certificate was issued by a CA without
# an organisation in its subject, so the CA subject carries O as well.
make_ca() { # dir, common name
    [ -f "$1/ca.pem" ] && return 0
    mkdir -p "$1"
    openssl req -x509 -newkey rsa:3072 -nodes -days "$DAYS" \
        -keyout "$1/ca-key.pem" -out "$1/ca.pem" \
        -subj "/C=NL/O=Grip lokale omgeving/CN=$2" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
}

issue() { # ca dir, out dir, subject, dns name
    [ -f "$2/cert.pem" ] && return 0
    mkdir -p "$2"
    openssl req -newkey rsa:3072 -nodes -keyout "$2/key.pem" -out "$2/req.csr" \
        -subj "$3" 2>/dev/null
    printf '%s\n' \
        "subjectAltName=DNS:$4" \
        'basicConstraints=CA:FALSE' \
        'keyUsage=critical,digitalSignature,keyEncipherment' \
        'extendedKeyUsage=serverAuth,clientAuth' > "$2/ext.cnf"
    openssl x509 -req -in "$2/req.csr" -CA "$1/ca.pem" -CAkey "$1/ca-key.pem" \
        -CAcreateserial -days "$DAYS" -extfile "$2/ext.cnf" -out "$2/cert.pem" 2>/dev/null
    rm -f "$2/req.csr" "$2/ext.cnf"
    # The FSC images run as an unprivileged user and read the key from a
    # read-only mount.
    chmod 644 "$2/key.pem"
}

make_ca "$pki/group" "grip lokale FSC-groep"

peer() { # key, peer id, organisation name, components with a group certificate
    key="$1"; peer_id="$2"; org="$3"; shift 3
    make_ca "$pki/internal/$key" "grip lokaal intern $key"
    for component in "$@"; do
        issue "$pki/group" "$pki/group/$key/$component" \
            "/C=NL/O=$org/CN=$component-$key/serialNumber=$peer_id" "$component-$key"
    done
    for component in manager controller inway outway txlog; do
        issue "$pki/internal/$key" "$pki/internal/$key/$component" \
            "/CN=$component-$key" "$component-$key"
    done
    # A client certificate for scripts that call the manager's internal API.
    issue "$pki/internal/$key" "$pki/internal/$key/admin" "/CN=admin-$key" "admin-$key"
}

# Peer ids are fictional and only unique within this group.
peer dir 01700000000000000099 "Lokale directory" manager
peer a 01700000000000000001 "DigiGilde voorbeeld" manager inway outway
peer b 01700000000000000002 "Voorbeeldministerie" manager inway outway

echo "FSC certificates in $pki"
