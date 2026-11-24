#!/bin/sh
# Runs at container start (the nginx image executes /docker-entrypoint.d/*.sh).
# Writes the part of the nginx configuration that handles /api/.
#
# BACKEND_URL set: this container passes /api/ on to the backend, so pages
#   and API share one address. The value is the backend as THIS container
#   reaches it, without a path, for example http://backend:8080.
# BACKEND_URL empty: something in front of this container (the platform's
#   router) sends /api/ to the backend itself. Nothing is proxied here, and
#   a request for /api/ that does arrive gets a plain answer instead of the
#   front page.
set -e
OUT=/tmp/grip-api.conf
if [ -n "${BACKEND_URL:-}" ]; then
    cat > "$OUT" <<CONF
location /api/ {
    proxy_pass ${BACKEND_URL};
    proxy_http_version 1.1;
    proxy_set_header Host \$grip_forwarded_host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$grip_forwarded_proto;
    proxy_set_header X-Forwarded-Host \$grip_forwarded_host;
    # The backend sets the security headers of its own answers (a closed
    # content policy among them). A header set here keeps the ones meant for
    # pages from being added on top.
    add_header X-Content-Type-Options "nosniff" always;
}
CONF
    echo "grip: /api/ is passed on to ${BACKEND_URL}"
else
    cat > "$OUT" <<'CONF'
location /api/ {
    default_type application/problem+json;
    add_header X-Content-Type-Options "nosniff" always;
    return 502 '{"title":"De API is hier niet bereikbaar","detail":"Dit adres stuurt /api/ niet door. Zet BACKEND_URL op de frontend, of laat het platform /api/ naar de backend sturen.","status":502}';
}
CONF
    echo "grip: BACKEND_URL is empty, /api/ is not passed on by this container"
fi

# Where someone reports a vulnerability (RFC 9116). SECURITY_TXT_URL is the
# security.txt of the organisation that runs this instance; this address
# sends the reader on to it, so one file is kept up to date. Without it the
# address answers 404 and not the front page.
#
# An example instance (INSTANCE_MODE=voorbeeld, ADR 0050) is a test
# environment, not production: it answers with a security.txt of its own that
# says so, keeps out of search engines, and ignores SECURITY_TXT_URL.
SECURITY_OUT=/tmp/grip-security.conf
if [ "${INSTANCE_MODE:-}" = "voorbeeld" ]; then
    if [ -n "${SECURITY_TXT_URL:-}" ]; then
        echo "grip: an example instance has its own security.txt; SECURITY_TXT_URL is ignored"
    fi
    # Written at start: Expires may lie at most a year ahead.
    expires="$(date -u -d "@$(($(date +%s) + 365 * 24 * 3600))" +%Y-%m-%dT%H:%M:%SZ)"
    cat > /tmp/grip-security.txt <<EOF
# Proefomgeving van grip, geen productie. Deze instantie bevat alleen
# verzonnen organisaties, personen en bedragen. Er draait hier geen dienst
# voor echt werk.
Contact: https://github.com/DigiGilde/grip/security/advisories/new
Policy: https://github.com/DigiGilde/grip/blob/main/SECURITY.md
Preferred-Languages: nl, en
Expires: $expires
EOF
    printf '%s\n' '# Proefomgeving van grip, geen productie: alleen verzonnen gegevens.' \
        'User-agent: *' 'Disallow: /' > /tmp/grip-robots.txt
    cat > "$SECURITY_OUT" <<'CONF'
set $grip_robots "noindex, nofollow";
location = /.well-known/security.txt {
    alias /tmp/grip-security.txt;
    # The RFC asks for the charset; the .txt extension would win over default_type.
    types { }
    default_type "text/plain; charset=utf-8";
    add_header Cache-Control "no-cache";
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Robots-Tag $grip_robots always;
}
location = /robots.txt {
    alias /tmp/grip-robots.txt;
    types { }
    default_type "text/plain; charset=utf-8";
    add_header Cache-Control "no-cache";
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Robots-Tag $grip_robots always;
}
CONF
    echo "grip: example instance, /.well-known/security.txt says it is a test environment"
else
case "${SECURITY_TXT_URL:-}" in
    https://*)
        case "$SECURITY_TXT_URL" in
            *[\'\"\;\{\}\ \$\\]*)
                echo "grip: SECURITY_TXT_URL has characters that do not belong in an address" >&2
                exit 64
                ;;
        esac
        cat > "$SECURITY_OUT" <<CONF
set \$grip_robots "";
location = /.well-known/security.txt {
    add_header X-Content-Type-Options "nosniff" always;
    return 302 ${SECURITY_TXT_URL};
}
CONF
        echo "grip: /.well-known/security.txt points to ${SECURITY_TXT_URL}"
        ;;
    "")
        cat > "$SECURITY_OUT" <<'CONF'
set $grip_robots "";
location = /.well-known/security.txt {
    add_header X-Content-Type-Options "nosniff" always;
    return 404;
}
CONF
        echo "grip: SECURITY_TXT_URL is empty, there is no security.txt"
        ;;
    *)
        echo "grip: SECURITY_TXT_URL must be an https address" >&2
        exit 64
        ;;
esac
fi
