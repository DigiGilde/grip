# Grip project commands

# Local development has no identity provider. Settings fails closed without
# one, so host-run tooling (alembic, pytest) needs this opt-in. Overridable
# from the environment; docker-compose sets the same default.
export DEV_NO_AUTH := env_var_or_default("DEV_NO_AUTH", "1")

# Default: list all available recipes
default:
    @just --list

# ---------------------------------------------------------------------------
# Development lifecycle
# ---------------------------------------------------------------------------

# Start all services (db + backend + frontend) in the foreground, with rebuild
dev:
    docker compose up --build

# Start all services in the background, with rebuild
up:
    docker compose up -d --build

# Start only the database (enough for host-run tests and migrations)
db:
    docker compose up -d --wait db

# Stop all services (keeps data)
down:
    docker compose down

# Stop all services and DELETE all data (volumes)
nuke:
    docker compose down -v

# Follow the logs of all services
logs:
    docker compose logs -f

# Open a psql shell in the database container
db-shell:
    docker compose exec db psql -U grip

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

# Run database migrations
migrate:
    cd backend && uv run alembic upgrade head

# Create a new migration (auto-generated from model changes)
migration NAME:
    cd backend && uv run alembic revision --autogenerate -m "{{ NAME }}"

# Drop everything in the local database and run the migrations again
reset-db:
    docker compose exec -T db psql -U grip -d grip -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    cd backend && uv run alembic upgrade head

# To act as an example person, set the cookie `grip_dev_person` to an id the
# seed prints: document.cookie = "grip_dev_person=<id>; path=/" in the browser.
# Without the cookie you are the first active beheerder.
# `--dataset NAME` picks the dataset (default SEED_DATASET: voorbeeld; also programma,
# bzk, gdi, odi, ezk and nldd, the instances of the example chain).
# Load fictional example data into an empty local database (`just seed --reset` empties it first)
seed *ARGS:
    cd backend && uv run python -m grip.dev.seed {{ ARGS }}

# Fictional data at the size of a real organisation (150 people, 400
# assignments over four years), to measure speed with `just check-speed`.
# Takes several minutes; use a database of its own (DATABASE_URL).
seed-scale *ARGS:
    cd backend && uv run python -m grip.dev.seed_scale {{ ARGS }}

# Walk an example assignment along the path, one committed step at a time, and
# look back at each moment on Geschiedenis of the assignment. Uses DATABASE_URL; needs a seeded
# database and no containers of its own. `--days N` lays the facts N days apart,
# `--geen-goedkeuring` leaves internal approval as it is set.
kroniek-nieuw *ARGS:
    cd backend && uv run python -m grip.dev.chronicle_walk new {{ ARGS }}

# The next step of this assignment, chosen from the course the screens read
kroniek-stap ID *ARGS:
    cd backend && uv run python -m grip.dev.chronicle_walk next {{ ID }} {{ ARGS }}

# Compare the tables of every assignment with its chronicle
kroniek-check:
    cd backend && uv run python -m grip.chronicle.check

# Write what differs back from the chronicle of this assignment
kroniek-herstel ID:
    cd backend && uv run python -m grip.dev.chronicle_walk rebuild {{ ID }}

# `just seed --extend` adds the corpus peers and the context of the example
# assignments to data that was seeded earlier; a fresh seed includes them.
# The dev backend reaches the stand-in as its outway: start the backend with
#   OUTWAY_URL=http://127.0.0.1:8040
# Nothing else is needed for context and the node picker: outbound
# federation (FEDERATION_OUTBOUND_ENABLED) stays off and INSTANCE_TOOI_URI
# stays empty. A backend in a container uses http://host.docker.internal:8040.
# Start the stand-in corpus for local development on port 8040 (fictional nodes, corpus-context v1)
corpus-standin PORT="8040":
    cd backend && uv run uvicorn grip.dev.corpus_standin.app:app --port {{ PORT }}

# Fetches the organisation export of organisaties.overheid.nl and brings the
# list of organisations in line with it. `--file PATH` applies a download.
# Take over the government organisations from the public register (see docs/organisaties.md)
sync-organisations *ARGS:
    cd backend && uv run python -m grip.integrations.organisations {{ ARGS }}

# Load the families, groups and scales of the Functiegebouw Rijk from the
# reference file in the repo (`--file PATH` for another file in that format)
load-function-framework *ARGS:
    cd backend && uv run python -m grip.integrations.function_framework {{ ARGS }}

# Needs the link with Wies (WIES_BASE_URL and WIES_API_KEY); without it the
# catalogue is kept by hand under Beheer.
# Take over the roles from the skills of Wies (see docs/rollen.md)
sync-roles:
    cd backend && uv run python -m grip.integrations.wies.sync_roles

# Subcommands: inspect, check, propose, confirm, load, reconcile. Paths are
# relative to where you call it, for example
# `just import-grist inspect ../import/document.grist`.
# Import from a Grist document download (see docs/import-grist.md)
import-grist *ARGS:
    cd "{{ invocation_directory() }}" && uv run --project "{{ justfile_directory() }}/backend" python -m grip.importers.grist {{ ARGS }}

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

# Run the backend and frontend tests (backend needs the database: `just db`)
test: test-backend test-frontend

# Run the backend tests
test-backend:
    cd backend && uv run pytest

# Run the frontend tests
test-frontend:
    cd frontend && npm run test

# Lint backend and frontend
lint:
    cd backend && uv run ruff check . && uv run ruff format --check .
    cd frontend && npm run lint

# Format the backend code
format:
    cd backend && uv run ruff format .

# Type check the frontend
typecheck:
    cd frontend && npm run typecheck

# Install frontend dependencies
install-frontend:
    cd frontend && npm install

# ---------------------------------------------------------------------------
# Federation
# ---------------------------------------------------------------------------

# Lint the contract against the API Design Rules, validate its examples and build its reading pages
contract-check:
    cd backend/grip/federation/contract && npm ci && npm run lint && npm run validate && npm run docs

# ---------------------------------------------------------------------------
# The example FSC group on ZAD (deploy/zad/fsc; see docs/uitrol-zad.md)
# ---------------------------------------------------------------------------

# Needs BASE_DOMAIN, PROJECT and DEPLOYMENT_DIR, _A, _B, _D, _E, _G, _O and _Z, as pki.sh does.
# Writes <component>.env for zadctl env add and, for a component with a
# database, <component>.alias for zadctl alias add, into
# ENV_DIR/<deployment> (default ENV_DIR: deploy/zad/fsc/state/env). Stops
# when a placeholder is left or a TLS_* path is not one pki.sh mounts for that
# component (PKI_DIR as for pki.sh). For a deployment that already runs,
# `--existing <component>=<NAME>,<NAME>` names what the layer of that
# component already has: zadctl env add refuses a whole file with one of
# those, so their lines go to <component>.set.env, for zadctl env set
# (repeat it per component). `--dry-run` prints the files instead.
# Fill the FSC settings of one deployment of the example group from deploy/zad/fsc/env
[positional-arguments]
zad-fsc-env deployment *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    deployment="$1"
    shift
    dry_run=0
    # One "<component> <NAME>" per line.
    existing=""
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --dry-run) dry_run=1 ;;
            --existing)
                spec="${2:-}"
                if [[ ! "$spec" =~ ^[a-z0-9-]+=[^=]+$ ]]; then
                    echo "--existing takes <component>=<NAME>[,<NAME>...]" >&2
                    exit 2
                fi
                IFS=, read -r -a names <<< "${spec#*=}"
                for name in "${names[@]}"; do
                    [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "--existing: '$name' is not a variable name" >&2; exit 2; }
                    existing+="${spec%%=*} $name"$'\n'
                done
                shift ;;
            *) echo "unknown option: $1" >&2; exit 2 ;;
        esac
        shift
    done
    for var in BASE_DOMAIN PROJECT DEPLOYMENT_DIR DEPLOYMENT_A DEPLOYMENT_B DEPLOYMENT_D DEPLOYMENT_E DEPLOYMENT_G DEPLOYMENT_O DEPLOYMENT_Z; do
        [ -n "${!var:-}" ] || { echo "$var is not set" >&2; exit 1; }
        export "${var?}"
    done
    case "$deployment" in
        "$DEPLOYMENT_DIR") peer=dir; templates="directory-manager directory-ui" ;;
        "$DEPLOYMENT_A") peer=a ;;
        "$DEPLOYMENT_B") peer=b ;;
        "$DEPLOYMENT_D") peer=d ;;
        "$DEPLOYMENT_E") peer=e ;;
        "$DEPLOYMENT_G") peer=g ;;
        "$DEPLOYMENT_O") peer=o ;;
        "$DEPLOYMENT_Z") peer=z ;;
        *) echo "$deployment is none of DEPLOYMENT_DIR, DEPLOYMENT_A, DEPLOYMENT_B, DEPLOYMENT_D, DEPLOYMENT_E, DEPLOYMENT_G, DEPLOYMENT_O and DEPLOYMENT_Z" >&2; exit 1 ;;
    esac
    if [ "$peer" != dir ]; then
        templates=""
        for role in frontend grip federation manager controller inway outway txlog bootstrap; do
            templates="$templates $peer-$role"
        done
    fi
    component_of() {
        case "$1" in
            directory-manager) echo dirmgr ;;
            directory-ui) echo dirui ;;
            *-frontend) echo component-1 ;;
            *-grip) echo component-2 ;;
            *-bootstrap) echo "fscboot-$peer" ;;
            *) echo "${1#*-}" ;;
        esac
    }
    components=""
    for template in $templates; do
        components="$components $(component_of "$template")"
    done
    fsc=deploy/zad/fsc
    while read -r component name; do
        [ -n "$component" ] || continue
        case "$components " in
            *" $component "*) ;;
            *) echo "--existing: $component is not a component of $deployment:$components" >&2; exit 2 ;;
        esac
        for template in $templates; do
            if [ "$(component_of "$template")" = "$component" ] && ! grep -q "^$name=" "$fsc/env/$template.env"; then
                echo "--existing: $template.env sets no $name, so $component has nothing to set for it" >&2
                exit 2
            fi
        done
    done <<< "$existing"
    out="${ENV_DIR:-$fsc/state/env}/$deployment"
    manifest="${PKI_DIR:-$fsc/state/pki}/upload/MANIFEST.tsv"
    [ -f "$manifest" ] || echo "No $manifest yet: the TLS_* paths are not compared with it." >&2
    # Only these: a plain envsubst also empties the $DATABASE_* of the alias.
    # shellcheck disable=SC2016
    placeholders='${BASE_DOMAIN} ${PROJECT} ${DEPLOYMENT_DIR} ${DEPLOYMENT_A} ${DEPLOYMENT_B} ${DEPLOYMENT_D} ${DEPLOYMENT_E} ${DEPLOYMENT_G} ${DEPLOYMENT_O} ${DEPLOYMENT_Z}'
    [ "$dry_run" = 1 ] || mkdir -p "$out"
    commands=""
    aliases=""
    for template in $templates; do
        component="$(component_of "$template")"
        filled="$(envsubst "$placeholders" < "$fsc/env/$template.env" | grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$')"
        values="$(grep -v '^STORAGE_POSTGRES_DSN=' <<< "$filled" || true)"
        alias="$(grep '^STORAGE_POSTGRES_DSN=' <<< "$filled" || true)"
        if grep -n -e '\$' -e '=<.*>$' <<< "$values"; then
            echo "$template.env: a placeholder is left (above)" >&2
            exit 1
        fi
        if [ -n "$alias" ] && grep -oE '\$\{?[A-Za-z_]+' <<< "$alias" | grep -vE '^\$\{?DATABASE_'; then
            echo "$template.env: the alias refers to more than \$DATABASE_* (above)" >&2
            exit 1
        fi
        while IFS='=' read -r name path; do
            case "$path" in
                "/etc/fsc/$peer/"*) ;;
                *) echo "$template.env: $name is not under /etc/fsc/$peer/" >&2; exit 1 ;;
            esac
            if [ -f "$manifest" ] && ! awk -F'\t' -v d="$deployment" -v c="$component" -v p="$path" \
                '$1 == d && $2 == c && $4 == p { found = 1 } END { exit !found }' "$manifest"; then
                echo "$template.env: $name=$path is not in $manifest for $component" >&2
                exit 1
            fi
        done < <(grep '^TLS_[A-Z_]*=' <<< "$values" || true)
        new=""
        changed=""
        while IFS= read -r line; do
            [ -n "$line" ] || continue
            if grep -qxF "$component ${line%%=*}" <<< "$existing"; then
                changed+="$line"$'\n'
            else
                new+="$line"$'\n'
            fi
        done <<< "$values"
        # The bootstrap runs in one deployment only: its values are component-wide.
        layer=" --deployment $deployment"
        [ "$component" != "fscboot-$peer" ] || layer=""
        for kind in env set.env; do
            file="$out/$component.$kind"
            if [ "$kind" = env ]; then lines="$new"; verb="add"; else lines="$changed"; verb="set"; fi
            if [ -z "$lines" ]; then
                [ "$dry_run" = 1 ] || [ ! -f "$file" ] || echo "$file is left from an earlier run; the commands below do not use it" >&2
                continue
            fi
            if [ "$dry_run" = 1 ]; then
                printf 'would write %s:\n%s' "$file" "$lines"
            else
                printf '%s' "$lines" > "$file"
            fi
            commands+="  zadctl env $verb -c $component$layer --env-file $file"$'\n'
        done
        if [ -n "$alias" ]; then
            if [ "$dry_run" = 1 ]; then
                printf 'would write %s:\n%s\n' "$out/$component.alias" "$alias"
            else
                printf '%s\n' "$alias" > "$out/$component.alias"
            fi
            aliases+="  zadctl alias add -c $component --env-file $out/$component.alias"$'\n'
        fi
    done
    echo
    echo "From the checkout that holds .env.zadctl, inside a rollout window of"
    echo "docs/uitrol-zad.md: after zadctl config set rollout false and the deployment"
    echo "create or assign of these components, before zadctl project refresh and"
    echo "zadctl config set rollout true:"
    printf '%s' "$commands"
    if [ -n "$aliases" ]; then
        echo "Once per component, by the first deployment that runs it (one alias serves them all):"
        printf '%s' "$aliases"
    fi
    if [ "$peer" != dir ]; then
        echo "Through stdin, never in a file (docs/uitrol-zad.md): FEDERATION_SIGNING_KEY on"
        echo "component-2 and federation, a new key per instance once instance-signing-key is"
        echo "off component-2; SESSION_SECRET_KEY on federation, and on component-2 of a new"
        echo "instance; PEER_REGISTRY_KEY, one value, on component-2 and fscboot-$peer."
    fi

# Needs the output of deploy/zad/fsc/pki.sh (PKI_DIR, default
# deploy/zad/fsc/state/pki). Uploads every file MANIFEST.tsv lists for the
# deployment as attachment fsc-<deployment>-<component>-<file> of its
# component, on its pod path, replacing what is there. Saves without rolling
# out: `zadctl project refresh` afterwards. Runs zadctl in the checkout that
# holds .env.zadctl. `--dry-run` prints the zadctl commands instead.
# Upload and couple the FSC certificates of one deployment of the example group
[positional-arguments]
zad-fsc-attachments deployment *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    deployment="$1"
    shift
    dry_run=0
    for flag in "$@"; do
        case "$flag" in
            --dry-run) dry_run=1 ;;
            *) echo "unknown option: $flag" >&2; exit 2 ;;
        esac
    done
    pki="${PKI_DIR:-deploy/zad/fsc/state/pki}"
    manifest="$pki/upload/MANIFEST.tsv"
    [ -f "$manifest" ] || { echo "No $manifest: run deploy/zad/fsc/pki.sh first." >&2; exit 1; }
    count=0
    while IFS=$'\t' read -r row_deployment component file pod_path; do
        [ "$row_deployment" = "$deployment" ] || continue
        source="$pki/upload/$deployment/$component/$file"
        [ -f "$source" ] || { echo "$source is missing" >&2; exit 1; }
        command=(zadctl --no-rollout attachment assign "fsc-$deployment-$component-${file%.pem}" "$component"
            --from-file "$source" --mount-path "$pod_path" --replace --upsert --yes)
        if [ "$dry_run" = 1 ]; then
            printf '%q ' "${command[@]}"
            echo
        else
            "${command[@]}" < /dev/null
        fi
        count=$((count + 1))
    done < <(tail -n +2 "$manifest")
    [ "$count" -gt 0 ] || { echo "$manifest lists nothing for $deployment" >&2; exit 1; }
    if [ "$dry_run" = 1 ]; then
        echo "($count attachments)"
    else
        echo "$count attachments saved, not rolled out (zadctl project pending lists them); the zadctl project refresh at the end of the rollout window rolls them out"
    fi

# ---------------------------------------------------------------------------
# Local environment (built images, own compose project; see docs/lokaal.md)
# ---------------------------------------------------------------------------

# Build the images for the local environment (SOURCE: tree or head)
local-build SOURCE="tree":
    deploy/local/local.sh build {{ SOURCE }}

# Start the local environment (MODE: one, keycloak, sso, fsc, fsc-keycloak, fsc-corpus, fsc-voorbeeld)
local-up MODE="one":
    deploy/local/local.sh up {{ MODE }}

# Publish the services, make the FSC contracts and fill grip's peer registry (--voorbeeld: mark the peers as example)
local-fsc-init *ARGS:
    deploy/local/local.sh fsc-init {{ ARGS }}

# Show where the local environment listens and what is running
local-urls:
    deploy/local/local.sh urls

# Stop the local environment (keeps data)
local-down:
    deploy/local/local.sh down

# Stop the local environment and delete its data, certificates and secrets
local-nuke:
    deploy/local/local.sh nuke

# Add the local Bouwmeester to the FSC group as a corpus system (peer C)
local-fsc-corpus-init:
    deploy/local/local.sh fsc-corpus-init

# ---------------------------------------------------------------------------
# Bouwmeester and Wies next to grip (run from their checkouts; docs/lokaal.md)
# ---------------------------------------------------------------------------

# Start a local Bouwmeester from its checkout (DIR is remembered after the first time)
bouwmeester-up DIR="":
    BOUWMEESTER_DIR="{{ DIR }}" deploy/local/bouwmeester.sh up

# Stop the local Bouwmeester (keeps data)
bouwmeester-down:
    deploy/local/bouwmeester.sh down

# Start a local Wies from its checkout (DIR is remembered after the first time)
wies-up DIR="":
    WIES_DIR="{{ DIR }}" deploy/local/wies.sh up

# Let the local Wies pull opdrachten, roles and placements from grip
wies-sync:
    deploy/local/wies.sh sync

# Stop the local Wies (keeps data)
wies-down:
    deploy/local/wies.sh down

# Dev outway and grip's federation listener: grip and Bouwmeester without FSC
dev-link-up:
    deploy/local/dev-link.sh up

# Register grip in the local Bouwmeester and the other way around
dev-link-peers:
    deploy/local/dev-link.sh peers

# Stop the dev outway and grip's federation listener
dev-link-down:
    deploy/local/dev-link.sh down

# Only the dev outway, with your own routes file (see grip.dev.dev_outway)
dev-outway ROUTES PORT="9230":
    cd backend && DEV_OUTWAY_ROUTES="{{ absolute_path(ROUTES) }}" uv run uvicorn grip.dev.dev_outway:create_app --factory --port {{ PORT }}

# A local mail catcher: what grip mails lands in its inbox and nowhere else
mail-up:
    deploy/local/mail.sh up

# Stop the local mail catcher
mail-down:
    deploy/local/mail.sh down

# The worker (outbox, tasks, mail) against a database, with the local mail catcher
worker-with-mail database_url="postgresql+asyncpg://grip:grip@localhost:5434/grip":
    #!/usr/bin/env bash
    set -euo pipefail
    set -a
    eval "$(deploy/local/mail.sh env)"
    set +a
    export DEV_NO_AUTH=1 DATABASE_URL="{{database_url}}"
    cd backend
    exec uv run python -m grip.worker

# Start the backend with the example data on port 8010, as a Rijksorganisatie:
# documents carry the Rijkslint and the Rijkshuisstijl typeface.
preview port="8010":
    #!/usr/bin/env bash
    set -euo pipefail
    root="$(pwd)"
    set -a
    eval "$(deploy/local/dev-link.sh env)"
    eval "$(deploy/local/wies.sh env)"
    set +a
    export DEV_NO_AUTH=1
    export INSTANCE_NAME="Grip DigiGilde (voorbeeld)"
    export DATABASE_URL="${PREVIEW_DATABASE_URL:-postgresql+asyncpg://grip:grip@localhost:5434/grip_preview}"
    export LETTERHEAD_LOGO_PATH="$root/frontend/node_modules/@nldd/design-system/dist/favicon.svg"
    export DOCUMENT_FONT_DIR="$root/frontend/node_modules/@nldd/design-system/dist/fonts"
    # Drafting texts locally: the command-line tool with your own login, when
    # it is installed and no model was chosen. Development only (ADR 0035).
    if [ -z "${LLM_PROVIDER:-}" ] && [ -z "${VLAM_API_KEY:-}" ] && command -v claude >/dev/null 2>&1; then
        export LLM_PROVIDER=claude_cli
    fi
    cd backend
    uv run alembic upgrade head
    exec uv run uvicorn grip.core.app:create_app --factory --port {{port}}

# Take the sender, the sections and the standard texts of a quote from a shipped profile
quote-profile NAME:
    cd backend && uv run python -m grip.dev.quote_profile {{ NAME }}

# Rebuild favicon, app icons and the images in docs/merk from frontend/brand/mark.svg
brand:
    cd frontend && node scripts/build-brand.mjs

# Remove the request forms of vacancies that closed longer ago than the instance keeps them
vacancy-forms-retention:
    cd backend && uv run python -m grip.services.vacancies.request_forms

# Run the daily retention round once, as the worker does at RETENTION_HOUR
retention-run:
    cd backend && uv run python -m grip.services.retention

# Bring an example database from before the rule on who judges something internal
# in line with today's seed (a director approves vacancies; client-side people have
# no inzetschaal). Idempotent; only touches persons in the example domain.
fix-internal-judges:
    cd backend && uv run python -m grip.dev.fix_internal_judges

# Make the role typed in as "po" the role Product owner, on an existing database (can be repeated)
fix-role-po:
    cd backend && uv run python -m grip.dev.fix_role_po

# Turn open places an earlier version wrote for a known fact ("[vul aan: de schaal van de vacature]")
# back into that fact, in draft vacancy texts and standard texts. Idempotent; --check only counts.
fix-open-places *ARGS:
    cd backend && uv run python -m grip.dev.fix_open_places {{ARGS}}

# Store the naverrekeningen that stand open (once, after migration 0036_billing_correction)
billing-corrections-sync:
    cd backend && uv run python -m grip.services.billing_corrections

# Measure spacing of every page in a headless browser (servers must be running; see docs/ontwerp.md)
check-spacing *ARGS:
    cd frontend && node scripts/check-spacing.mjs {{ARGS}}

# Open every page as every kind of reader: does it settle, say no access where the
# server refuses, and offer no action or amount the reader may not have (see docs/toegang.md)
[positional-arguments]
check-access *ARGS:
    cd frontend && node scripts/check-access.mjs "$@"

# Run axe-core on every page in a real browser, as three kinds of reader, wide
# and narrow, dark and light; `--open` also opens forms and menus. Needs
# running servers and a host name of your own in --base. See
# docs/toegankelijkheid.md for what a machine cannot find.
[positional-arguments]
check-a11y *ARGS:
    cd frontend && node scripts/check-a11y.mjs "$@"

# Measure how fast every page is for every kind of reader, against the budget
# (servers must be running on a database of real size; see docs/snelheid.md)
[positional-arguments]
check-speed *ARGS:
    cd frontend && node scripts/check-speed.mjs "$@"

# First login through the real SSO Rijk: starts grip against deploy/local/.env.sso
# and shows, masked, what the provider sent and what grip did with it
sso-check port="9011":
    #!/usr/bin/env bash
    set -euo pipefail
    env_file="deploy/local/.env.sso"
    [ -f "$env_file" ] || { echo "Kopieer deploy/local/.env.sso.example naar $env_file en vul hem in (zie docs/lokaal.md)."; exit 1; }
    set -a
    . "$env_file"
    set +a
    [ -n "${OIDC_CLIENT_SECRET:-}" ] || { echo "OIDC_CLIENT_SECRET in $env_file is leeg."; exit 1; }
    [ -n "${SESSION_SECRET_KEY:-}" ] || { echo "SESSION_SECRET_KEY in $env_file is leeg (openssl rand -hex 32)."; exit 1; }
    export DEV_NO_AUTH=0 OIDC_DIAGNOSTICS=1
    export FRONTEND_URL="http://localhost:{{port}}" BACKEND_URL="http://localhost:{{port}}"
    export INSTANCE_NAME="Grip (controle SSO Rijk)"
    export DATABASE_URL="postgresql+asyncpg://grip:grip@localhost:5434/grip_sso_check"
    docker compose exec -T db psql -U grip -d postgres -Atc "select 1 from pg_database where datname='grip_sso_check'" | grep -q 1 \
        || docker compose exec -T db psql -U grip -d postgres -qc "create database grip_sso_check"
    cd backend
    uv run alembic upgrade head
    echo
    echo "1. Open http://localhost:{{port}}/api/auth/login en log in met SSO Rijk."
    echo "2. Je komt uit op het verslag. Open daarna http://localhost:{{port}}/api/auth/diagnose/reauth"
    echo "   en let op of je opnieuw moet inloggen."
    echo "3. Kopieer het verslag op http://localhost:{{port}}/api/auth/diagnose. Stop met Ctrl+C."
    echo
    exec uv run uvicorn grip.core.app:create_app --factory --port {{port}}

# Make a key pair for notifications (web push); put the line in backend/.env
push-key:
    cd backend && DEV_NO_AUTH=1 uv run python -m grip.integrations.push.keys

# Put an example instance (INSTANCE_MODE=voorbeeld) back to its starting state
example-reset:
    cd backend && uv run python -m grip.core.example

# ---------------------------------------------------------------------------
# Ontwikkelportaal (static site over docs/; see docs/lokaal.md)
# ---------------------------------------------------------------------------

# Build the ontwikkelportaal into ontwikkelportaal/dist with its search index, and check links and scripts
ontwikkelportaal:
    cd ontwikkelportaal && npm ci --ignore-scripts && npm run build && npm run check

# Run the ontwikkelportaal with live reload while editing docs/ or ontwikkelportaal/ (search needs a build first)
ontwikkelportaal-dev:
    cd ontwikkelportaal && npm run dev
