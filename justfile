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
