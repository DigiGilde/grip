#!/bin/sh
# Modelled on deploy/zad/controller-migrate/entrypoint.sh in MinBZK/moza-fsc-testnet.
# Runs the migrations of the OpenFSC controller, then serves with the
# environment the component already has.
set -eu

DSN="${STORAGE_POSTGRES_DSN:-}"
if [ -z "$DSN" ]; then
    echo "STORAGE_POSTGRES_DSN is not set" >&2
    exit 1
fi

# `migrate up` reads --postgres-dsn, not STORAGE_POSTGRES_DSN. It runs on every
# start and takes a lock; run one replica.
echo "controller: running migrations"
/usr/local/bin/controller migrate up --postgres-dsn "$DSN"

echo "controller: starting"
exec /usr/local/bin/controller serve
