#!/bin/sh
# Writes /tmp/ontwikkelportaal-config.json from ONTWIKKELPORTAAL_INSTANCES, at start.
# The html directory is not writable for the unprivileged user, so nginx serves
# this file from /tmp. The start page validates each entry itself.
set -eu

printf '{"instances":%s}\n' "${ONTWIKKELPORTAAL_INSTANCES:-[]}" > /tmp/ontwikkelportaal-config.json
