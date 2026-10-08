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
# Load fictional example data into an empty local database (`just seed --reset` empties it first)
seed *ARGS:
    cd backend && uv run python -m grip.dev.seed {{ ARGS }}

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

# Refresh the vendored contract from a checkout of the contract repo
sync-contract CHECKOUT:
    cd backend && uv run python -m grip.federation.sync_contract "{{ absolute_path(CHECKOUT) }}"

# ---------------------------------------------------------------------------
# Local environment (built images, own compose project; see docs/lokaal.md)
# ---------------------------------------------------------------------------

# Build the images for the local environment (SOURCE: tree or head)
local-build SOURCE="tree":
    deploy/local/local.sh build {{ SOURCE }}

# Start the local environment (MODE: one, keycloak, sso, fsc, fsc-keycloak)
local-up MODE="one":
    deploy/local/local.sh up {{ MODE }}

# Publish the services, make the FSC contracts and fill grip's peer registry
local-fsc-init:
    deploy/local/local.sh fsc-init

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
    cd backend
    uv run alembic upgrade head
    exec uv run uvicorn grip.core.app:create_app --factory --port {{port}}
