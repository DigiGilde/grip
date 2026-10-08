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
