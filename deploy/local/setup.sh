#!/bin/sh
# Generate what the local environment needs and what must not be in the
# repo: secrets, the Keycloak realm with one fictional user, and env files.
# Everything lands in ./state (gitignored). Safe to run again: existing
# values are kept unless you pass --fresh.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
state="$here/state"
[ "${1:-}" = "--fresh" ] && rm -rf "$state/secrets.env" "$state/keycloak" "$state/tls"
mkdir -p "$state/keycloak"

rand() { openssl rand -hex "${1:-24}"; }

if [ ! -f "$state/secrets.env" ]; then
    cat > "$state/secrets.env" <<SECRETS
SESSION_SECRET_KEY=$(rand 32)
SESSION_SECRET_KEY_B=$(rand 32)
KEYCLOAK_ADMIN_PASSWORD=$(rand 12)
KEYCLOAK_CLIENT_SECRET=$(rand 24)
KEYCLOAK_USER_PASSWORD=$(rand 12)
SECRETS
fi
# shellcheck disable=SC1091
. "$state/secrets.env"

# The application refuses to send tokens to an identity provider over plain
# http, also locally. So the local Keycloak gets TLS: a private CA and one
# certificate, valid for the name the browser uses (localhost) and the name
# the backend uses (keycloak). The backend trusts the CA through a bundle
# that also holds the public CAs, so a real provider keeps working.
tls="$state/tls"
if [ ! -f "$tls/keycloak.crt" ]; then
    mkdir -p "$tls"
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
        -keyout "$tls/ca.key" -out "$tls/ca.crt" \
        -subj "/CN=grip lokale omgeving CA" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
    openssl req -newkey rsa:2048 -nodes \
        -keyout "$tls/keycloak.key" -out "$tls/keycloak.csr" \
        -subj "/CN=keycloak" 2>/dev/null
    printf '%s\n' \
        'subjectAltName=DNS:keycloak,DNS:localhost,IP:127.0.0.1' \
        'basicConstraints=CA:FALSE' \
        'keyUsage=critical,digitalSignature,keyEncipherment' \
        'extendedKeyUsage=serverAuth' > "$tls/san.cnf"
    openssl x509 -req -in "$tls/keycloak.csr" -CA "$tls/ca.crt" -CAkey "$tls/ca.key" \
        -CAcreateserial -days 825 -extfile "$tls/san.cnf" -out "$tls/keycloak.crt" 2>/dev/null
    chmod 644 "$tls/keycloak.key"
fi
# Public CAs from the backend image plus the local CA.
if [ ! -f "$tls/ca-bundle.crt" ]; then
    docker run --rm --entrypoint python grip-local/backend \
        -c "import certifi,sys;sys.stdout.write(open(certifi.where()).read())" > "$tls/ca-bundle.crt"
    cat "$tls/ca.crt" >> "$tls/ca-bundle.crt"
fi

# A realm with one confidential client and two fictional people: one who is
# known in grip (bootstrapped as beheerder) and one who is not, to see the
# "geen toegang" path. The user ids are fixed: Keycloak keeps no data here,
# and grip binds a person to the subject on first login, so a new id after
# every restart would lock the person out.
cat > "$state/keycloak/grip-realm.json" <<REALM
{
  "realm": "grip",
  "enabled": true,
  "sslRequired": "none",
  "registrationAllowed": false,
  "clients": [
    {
      "clientId": "grip",
      "enabled": true,
      "protocol": "openid-connect",
      "publicClient": false,
      "secret": "$KEYCLOAK_CLIENT_SECRET",
      "standardFlowEnabled": true,
      "directAccessGrantsEnabled": false,
      "redirectUris": [
        "http://localhost:9001/api/auth/callback",
        "http://localhost:9002/api/auth/callback"
      ],
      "webOrigins": ["http://localhost:9001", "http://localhost:9002"],
      "attributes": {
        "pkce.code.challenge.method": "S256",
        "post.logout.redirect.uris": "http://localhost:9001/*##http://localhost:9002/*"
      }
    }
  ],
  "users": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "username": "testbeheerder",
      "enabled": true,
      "emailVerified": true,
      "email": "testbeheerder@grip.invalid",
      "firstName": "Test",
      "lastName": "Beheerder",
      "credentials": [
        {"type": "password", "value": "$KEYCLOAK_USER_PASSWORD", "temporary": false}
      ]
    },
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "username": "onbekend",
      "enabled": true,
      "emailVerified": true,
      "email": "onbekend@grip.invalid",
      "firstName": "Onbekende",
      "lastName": "Bezoeker",
      "credentials": [
        {"type": "password", "value": "$KEYCLOAK_USER_PASSWORD", "temporary": false}
      ]
    }
  ]
}
REALM

# Without login: the application runs as a stand-in beheerder.
cat > "$state/noauth.env" <<ENV
DEV_NO_AUTH=1
SESSION_SECRET_KEY=$SESSION_SECRET_KEY
SESSION_SECRET_KEY_B=$SESSION_SECRET_KEY_B
ENV

# Login through the local Keycloak. The browser reaches it on
# https://localhost:9443; the backend reaches it inside the compose network,
# which is why discovery has its own address.
cat > "$state/keycloak.env" <<ENV
DEV_NO_AUTH=0
SESSION_SECRET_KEY=$SESSION_SECRET_KEY
SESSION_SECRET_KEY_B=$SESSION_SECRET_KEY_B
OIDC_ISSUER=https://localhost:9443/realms/grip
OIDC_DISCOVERY_URL=https://keycloak:8443/realms/grip/.well-known/openid-configuration
OIDC_CLIENT_ID=grip
OIDC_CLIENT_SECRET=$KEYCLOAK_CLIENT_SECRET
BOOTSTRAP_BEHEERDER_EMAILS=testbeheerder@grip.invalid
KEYCLOAK_ADMIN_PASSWORD=$KEYCLOAK_ADMIN_PASSWORD
ENV

echo "Generated in $state:"
echo "  noauth.env, keycloak.env, keycloak/grip-realm.json, tls/"
echo "Local Keycloak user: testbeheerder  (password in state/secrets.env)"
