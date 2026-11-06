#!/bin/sh
# Modelled on deploy/zad/txlog-migrate/entrypoint.sh in MinBZK/moza-fsc-testnet.
# Runs the migrations of the OpenFSC txlog-api, then serves with the
# environment the component already has.
set -eu

DSN="${STORAGE_POSTGRES_DSN:-}"
if [ -z "$DSN" ]; then
    echo "STORAGE_POSTGRES_DSN is not set" >&2
    exit 1
fi

# `migrate up` reads --postgres-dsn, not STORAGE_POSTGRES_DSN. It runs on every
# start and takes a lock; run one replica.
echo "txlog: running migrations"
/usr/local/bin/txlog-api migrate up --postgres-dsn "$DSN"

echo "txlog: starting"
exec /usr/local/bin/txlog-api serve
