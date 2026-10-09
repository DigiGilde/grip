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
}
CONF
    echo "grip: /api/ is passed on to ${BACKEND_URL}"
else
    cat > "$OUT" <<'CONF'
location /api/ {
    default_type application/problem+json;
    return 502 '{"title":"De API is hier niet bereikbaar","detail":"Dit adres stuurt /api/ niet door. Zet BACKEND_URL op de frontend, of laat het platform /api/ naar de backend sturen.","status":502}';
}
CONF
    echo "grip: BACKEND_URL is empty, /api/ is not passed on by this container"
fi
