#!/bin/sh
# Certificates for the example FSC group "grip-voorbeeld" on ZAD. A test CA
# for fictional instances; nothing here is PKIoverheid.
#
# Two kinds of trust, as FSC prescribes:
#   group     one CA for all peers. A certificate carries the peer id in the
#             subject serialNumber and the organisation name in O.
#   internal  one CA per peer, for the traffic between its own components.
#
# Needs: BASE_DOMAIN, PROJECT, DEPLOYMENT_DIR, DEPLOYMENT_A, DEPLOYMENT_B,
# DEPLOYMENT_D, DEPLOYMENT_E, DEPLOYMENT_G, DEPLOYMENT_O, DEPLOYMENT_Z (the ZAD
# base domain, the ZAD project and the deployment of each peer in it).
# Output goes to PKI_DIR (default: state/pki next to this script, gitignored):
#
#   group/ca.pem, group/ca-key.pem         the group CA
#   peers/<k>/...                          issued certificates, per peer
#   upload/<deployment>/<component>/*.pem  one directory per component in a
#                                          deployment, to upload as attachments
#   upload/MANIFEST.tsv                    deployment, component, file, pod path
#
# An attachment belongs to a component, and the deployments of the project
# share the components: every deployment that runs the manager gets all its
# attachments. So each peer has paths of its own in the pod, /etc/fsc/<k>/
# (k is a, b, d, e, g, o or z; dir for the directory), and the TLS_* settings of a
# deployment point at those of its own peer.
#
# A peer that is added keeps the others as they are. A peer whose deployment
# name changed keeps its old certificates, and the script warns: move its
# peers/<k> and upload/<old deployment> directories to the Trash and run again.
#
# Existing files are kept; pass --fresh to start over (the FSC databases must
# then be emptied as well: contracts are signed with the old keys).
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
PKI_DIR="${PKI_DIR:-$here/state/pki}"

for var in BASE_DOMAIN PROJECT DEPLOYMENT_DIR DEPLOYMENT_A DEPLOYMENT_B DEPLOYMENT_D DEPLOYMENT_E DEPLOYMENT_G DEPLOYMENT_O DEPLOYMENT_Z; do
    eval "[ -n \"\${$var:-}\" ]" || { echo "$var is not set" >&2; exit 1; }
done

if [ "${1:-}" = "--fresh" ] && [ -e "$PKI_DIR" ]; then
    trash "$PKI_DIR"
fi
mkdir -p "$PKI_DIR"
work="$PKI_DIR/.work"
mkdir -p "$work"

LEAF_DAYS=825
CA_DAYS=3650
# The platform takes attachments up to 64 KB.
MAX_ATTACHMENT_BYTES=65536

host() { # component, deployment
    printf '%s-%s-%s.%s' "$1" "$2" "$PROJECT" "$BASE_DOMAIN"
}

# The inway refuses a caller whose certificate was issued by a CA without an
# organisation in its subject, so the CA subject carries O as well.
make_ca() { # dir, common name
    [ -f "$1/ca.pem" ] && return 0
    mkdir -p "$1"
    openssl req -x509 -newkey rsa:3072 -nodes -days "$CA_DAYS" \
        -keyout "$1/ca-key.pem" -out "$1/ca.pem" \
        -subj "/C=NL/O=Grip voorbeeldomgeving/CN=$2" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
    chmod 600 "$1/ca-key.pem"
}

issue() { # ca dir, out dir, subject, subject alternative names (DNS:a,DNS:b)
    if [ -f "$2/cert.pem" ]; then
        first="${4%%,*}"
        openssl x509 -in "$2/cert.pem" -noout -ext subjectAltName 2>/dev/null | grep -qF "${first#DNS:}" ||
            echo "warning: $2/cert.pem does not carry ${first#DNS:}; keeping it" >&2
        return 0
    fi
    mkdir -p "$2"
    openssl req -newkey rsa:3072 -nodes -keyout "$2/key.pem" -out "$work/req.csr" \
        -subj "$3" 2>/dev/null
    printf '%s\n' \
        "subjectAltName=$4" \
        'basicConstraints=CA:FALSE' \
        'keyUsage=critical,digitalSignature,keyEncipherment' \
        'extendedKeyUsage=serverAuth,clientAuth' > "$work/ext.cnf"
    openssl x509 -req -in "$work/req.csr" -CA "$1/ca.pem" -CAkey "$1/ca-key.pem" \
        -CAcreateserial -days "$LEAF_DAYS" -extfile "$work/ext.cnf" \
        -out "$2/cert.pem" 2>/dev/null
    chmod 600 "$2/key.pem"
}

# A directory of attachment files for one component in one deployment.
manifest="$PKI_DIR/upload/MANIFEST.tsv"
mkdir -p "$PKI_DIR/upload"
printf 'deployment\tcomponent\tfile\tpod path\n' > "$manifest"

attach() { # deployment, component, file name, source file, pod path
    out="$PKI_DIR/upload/$1/$2"
    mkdir -p "$out"
    cp "$4" "$out/$3"
    size="$(wc -c < "$out/$3" | tr -d ' ')"
    [ "$size" -lt "$MAX_ATTACHMENT_BYTES" ] || { echo "$out/$3 is too large for an attachment" >&2; exit 1; }
    printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$5" >> "$manifest"
}

attach_group() { # deployment, component, peer key, directory with cert.pem and key.pem
    attach "$1" "$2" group-ca.pem "$PKI_DIR/group/ca.pem" "/etc/fsc/$3/group/ca.pem"
    attach "$1" "$2" group-cert.pem "$4/cert.pem" "/etc/fsc/$3/group/cert.pem"
    attach "$1" "$2" group-key.pem "$4/key.pem" "/etc/fsc/$3/group/key.pem"
}

attach_internal() { # deployment, component, peer key, internal dir, directory with cert.pem and key.pem
    attach "$1" "$2" internal-ca.pem "$4/ca.pem" "/etc/fsc/$3/internal/ca.pem"
    attach "$1" "$2" internal-cert.pem "$5/cert.pem" "/etc/fsc/$3/internal/cert.pem"
    attach "$1" "$2" internal-key.pem "$5/key.pem" "/etc/fsc/$3/internal/key.pem"
}

make_ca "$PKI_DIR/group" "grip voorbeeld FSC-groep"

# Peer ids are fictional and only unique within this group.
# key, deployment, peer id, organisation name
peer() {
    key="$1"; deployment="$2"; peer_id="$3"; org="$4"
    pdir="$PKI_DIR/peers/$key"
    idir="$pdir/internal"
    make_ca "$idir" "grip voorbeeld intern $key"

    if [ "$key" = "dir" ]; then
        manager=dirmgr
    else
        manager=manager
    fi

    # Group certificates: the hostname is in the SAN because standard TLS
    # clients (the directory UI) check it; the FSC mesh itself checks the peer id.
    for component in $group_components; do
        name="$component"
        [ "$component" = manager ] && name="$manager"
        issue "$PKI_DIR/group" "$pdir/group/$name" \
            "/C=NL/O=$org/CN=$(host "$name" "$deployment")/serialNumber=$peer_id" \
            "DNS:$(host "$name" "$deployment"),DNS:$name"
    done

    # Internal certificates: the controller, outway and inway check the
    # hostname of the manager and txlog they call. Within a deployment the
    # platform names a component <deployment>-<component>.
    for component in $internal_components; do
        name="$component"
        [ "$component" = manager ] && name="$manager"
        issue "$idir" "$idir/$name" "/CN=$name-$key" \
            "DNS:$(host "$name" "$deployment"),DNS:$deployment-$name,DNS:$name"
    done
    # A client certificate for the bootstrap, which calls the internal APIs of
    # manager and controller.
    issue "$idir" "$idir/admin" "/CN=admin-$key" "DNS:admin-$key"

    for component in $internal_components; do
        name="$component"
        [ "$component" = manager ] && name="$manager"
        attach_internal "$deployment" "$name" "$key" "$idir" "$idir/$name"
    done
    for component in $group_components; do
        name="$component"
        [ "$component" = manager ] && name="$manager"
        attach_group "$deployment" "$name" "$key" "$pdir/group/$name"
    done
    # The bootstrap component of a peer (bootstrap.sh in the image
    # fsc-bootstrap) presents the admin certificate.
    [ "$key" = "dir" ] || attach_internal "$deployment" "fscboot-$key" "$key" "$idir" "$idir/admin"
}

# The directory: a manager in directory mode, and a UI that presents the
# directory manager's own group certificate (the UI authenticates to the
# manager as the directory peer).
group_components=manager
internal_components=manager
peer dir "$DEPLOYMENT_DIR" 01800000000000000099 "Voorbeeldgroep directory"
attach_group "$DEPLOYMENT_DIR" dirui dir "$PKI_DIR/peers/dir/group/dirmgr"

group_components="manager inway outway"
internal_components="manager controller inway outway txlog"
peer a "$DEPLOYMENT_A" 01800000000000000001 "DigiGilde voorbeeld"
peer b "$DEPLOYMENT_B" 01800000000000000002 "Ministerie van BZK voorbeeld"
peer d "$DEPLOYMENT_D" 01800000000000000004 "MOZa voorbeeld"
peer e "$DEPLOYMENT_E" 01800000000000000005 "NLDD voorbeeld"
peer g "$DEPLOYMENT_G" 01800000000000000006 "GDI voorbeeld"
peer o "$DEPLOYMENT_O" 01800000000000000007 "ODI voorbeeld"
peer z "$DEPLOYMENT_Z" 01800000000000000008 "Ministerie van EZK voorbeeld"

trash "$work"

echo "FSC certificates in $PKI_DIR"
echo "Attachments per component in $PKI_DIR/upload (list: $manifest)"
echo
echo "The group CA key, $PKI_DIR/group/ca-key.pem, signs every peer in the"
echo "group. Never commit it and never upload it. It needs no safekeeping: the"
echo "group is an example, and --fresh makes a new one."
