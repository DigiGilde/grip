#!/bin/sh
# Log in for real through the local Keycloak, with curl following the same
# redirects a browser would: authorization code flow with PKCE, callback,
# session, status as that person, logout.
#
#   ./login-check.sh                 testbeheerder on instance A (port 9001)
#   ./login-check.sh onbekend        a person the instance does not know
#   ./login-check.sh testbeheerder 9002
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
. "$here/state/secrets.env"

user="${1:-testbeheerder}"
port="${2:-9001}"
base="http://localhost:$port"
jar="$(mktemp)"
page="$(mktemp)"
trap 'rm -f "$jar" "$page"' EXIT

step() { printf '\n== %s\n' "$1"; }

step "1. status before login"
curl -s --cacert "$here/state/tls/ca.crt" -c "$jar" -b "$jar" "$base/api/auth/status"; echo

step "2. /api/auth/login redirects to the identity provider"
auth_url="$(curl -s --cacert "$here/state/tls/ca.crt" -o /dev/null -c "$jar" -b "$jar" -w '%{redirect_url}' "$base/api/auth/login?next=/opdrachten")"
echo "$auth_url" | sed 's/&/\n   &/g' | head -12

step "3. the login form of the identity provider"
curl -s --cacert "$here/state/tls/ca.crt" -c "$jar" -b "$jar" -o "$page" "$auth_url"
action="$(grep -o 'action="[^"]*"' "$page" | head -1 | sed 's/action="//; s/"$//; s/&amp;/\&/g')"
[ -n "$action" ] || { echo "no login form found"; head -20 "$page"; exit 1; }
echo "form posts to: ${action%%\?*}"

step "4. submit credentials, receive the redirect back with a code"
callback="$(curl -s --cacert "$here/state/tls/ca.crt" -o /dev/null -c "$jar" -b "$jar" -w '%{redirect_url}' \
    --data-urlencode "username=$user" \
    --data-urlencode "password=$KEYCLOAK_USER_PASSWORD" \
    --data-urlencode "credentialId=" "$action")"
[ -n "$callback" ] || { echo "no redirect after submitting credentials"; exit 1; }
echo "$callback" | sed 's/code=[^&]*/code=<code>/; s/session_state=[^&]*/session_state=<..>/'

step "5. the callback exchanges the code and sets the session"
after="$(curl -s --cacert "$here/state/tls/ca.crt" -o /dev/null -c "$jar" -b "$jar" -w '%{http_code} -> %{redirect_url}' "$callback")"
echo "$after"

step "6. status after login"
curl -s --cacert "$here/state/tls/ca.crt" -c "$jar" -b "$jar" "$base/api/auth/status"; echo

step "7. logout"
out="$(curl -s --cacert "$here/state/tls/ca.crt" -o /dev/null -c "$jar" -b "$jar" -w '%{http_code} -> %{redirect_url}' "$base/api/auth/logout")"
echo "$out" | sed 's/id_token_hint=[^&]*/id_token_hint=<token>/'

step "8. status after logout"
curl -s --cacert "$here/state/tls/ca.crt" -c "$jar" -b "$jar" "$base/api/auth/status"; echo
