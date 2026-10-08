#!/bin/sh
# The local environment of grip. See docs/lokaal.md.
#
#   ./local.sh build [tree|head]   build the images (default: working tree)
#   ./local.sh up [mode]           start; mode is one of
#                                    one       one instance, no login (default)
#                                    keycloak  one instance, login through a local Keycloak
#                                    sso       one instance, login with SSO Rijk (.env.sso)
#                                    fsc       two instances with FSC between them, no login
#                                    fsc-keycloak   the same, with the local Keycloak
#   ./local.sh fsc-init            publish services, make contracts, fill the peer registry
#   ./local.sh check-login [user]  log in through the local Keycloak with curl
#   ./local.sh check-fsc           send one message from instance B to instance A
#   ./local.sh urls                where everything listens
#   ./local.sh logs [service...]   follow the logs
#   ./local.sh down                stop (keeps data)
#   ./local.sh nuke                stop and delete all data of this environment
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

all_files="-f compose.yml -f compose.fsc.yml"
all_profiles="--profile keycloak --profile two"

need_images() {
    docker image inspect grip-local/backend grip-local/frontend >/dev/null 2>&1 || ./build.sh
}

cmd="${1:-up}"
[ $# -gt 0 ] && shift

case "$cmd" in
    build)
        ./build.sh "${1:-tree}"
        ;;
    up)
        mode="${1:-one}"
        need_images
        ./setup.sh >/dev/null
        case "$mode" in
            one)
                docker compose -f compose.yml --env-file state/noauth.env up -d ;;
            keycloak)
                docker compose -f compose.yml --env-file state/keycloak.env --profile keycloak up -d ;;
            sso)
                [ -f .env.sso ] || { echo "Copy .env.sso.example to .env.sso and fill it in first."; exit 1; }
                docker compose -f compose.yml --env-file .env.sso up -d ;;
            fsc | fsc-keycloak)
                ./fsc-pki.sh >/dev/null
                if [ "$mode" = "fsc" ]; then
                    docker compose $all_files --env-file state/noauth.env --profile two up -d
                else
                    docker compose $all_files --env-file state/keycloak.env $all_profiles up -d
                fi
                echo "When everything is up: ./local.sh fsc-init" ;;
            *)
                echo "unknown mode '$mode'"; exit 64 ;;
        esac
        ./local.sh urls
        ;;
    fsc-init) ./fsc-bootstrap.sh ;;
    check-login) ./login-check.sh "$@" ;;
    check-fsc) ./fsc-send-check.sh ;;
    logs)
        # shellcheck disable=SC2086
        docker compose $all_files $all_profiles logs -f "$@" ;;
    down)
        # shellcheck disable=SC2086
        docker compose $all_files $all_profiles down ;;
    nuke)
        # shellcheck disable=SC2086
        docker compose $all_files $all_profiles down -v
        rm -rf state ;;
    urls)
        cat <<URLS

  Instance A, DigiGilde voorbeeld      http://localhost:9001
  Instance B, Voorbeeldministerie      http://localhost:9002   (modes fsc)
  Local Keycloak                       https://localhost:9443  (modes keycloak; admin / state/secrets.env)
  FSC controller, directory            http://localhost:9100   (modes fsc)
  FSC controller, peer A               http://localhost:9101
  FSC controller, peer B               http://localhost:9102

  Running now:
URLS
        docker compose $all_files $all_profiles ps --format '    {{.Service}}\t{{.Status}}' 2>/dev/null | sort
        ;;
    *)
        sed -n '2,17p' "$0"
        exit 64 ;;
esac
