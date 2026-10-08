#!/bin/sh
set -e

# Use the venv directly: `uv run` would try to re-install the project.
export PATH="/app/.venv/bin:$PATH"

echo "Running database migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn grip.core.app:create_app --factory --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='127.0.0.1'
