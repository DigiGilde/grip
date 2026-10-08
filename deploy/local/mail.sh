#!/bin/sh
# A local mail catcher next to the local grip: every message grip sends ends
# up in its inbox and goes nowhere else. See docs/lokaal.md.
#
#   ./mail.sh up        start the catcher (a container)
#   ./mail.sh env       the environment for the grip backend and the worker
#   ./mail.sh inbox     the messages it holds, newest first, as JSON
#   ./mail.sh status | down
set -eu

NAME=grip-local-mail
IMAGE="${MAIL_CATCHER_IMAGE:-axllent/mailpit:v1.20}"
SMTP_PORT="${MAIL_SMTP_PORT:-9325}"
WEB_PORT="${MAIL_WEB_PORT:-9326}"

case "${1:-status}" in
    up)
        if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
            echo "The mail catcher already runs."
        else
            docker rm -f "$NAME" >/dev/null 2>&1 || true
            docker run -d --name "$NAME" \
                -p "127.0.0.1:$SMTP_PORT:1025" -p "127.0.0.1:$WEB_PORT:8025" \
                "$IMAGE" >/dev/null
        fi
        echo "Inbox: http://127.0.0.1:$WEB_PORT"
        ;;
    env)
        # No TLS and no login: this relay only exists on this machine.
        echo "SMTP_HOST=127.0.0.1"
        echo "SMTP_PORT=$SMTP_PORT"
        echo "SMTP_FROM=noreply+grip-lokaal@voorbeeld.example"
        echo "SMTP_TLS=none"
        echo "MAIL_OUTBOX_INTERVAL_SECONDS=3"
        ;;
    inbox)
        curl -s "http://127.0.0.1:$WEB_PORT/api/v1/messages"
        ;;
    status)
        docker ps --filter "name=^$NAME$" --format '{{.Names}}: {{.Status}}' | grep . \
            || echo "The mail catcher does not run."
        ;;
    down)
        docker rm -f "$NAME" >/dev/null 2>&1 || true
        ;;
    *)
        echo "Usage: $0 up | env | inbox | status | down" >&2
        exit 2
        ;;
esac
