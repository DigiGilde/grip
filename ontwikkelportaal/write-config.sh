#!/bin/sh
# Writes /tmp/ontwikkelportaal-config.json from ONTWIKKELPORTAAL_INSTANCES, at start.
# The html directory is not writable for the unprivileged user, so nginx serves
# this file from /tmp. The start page validates each entry itself.
set -eu

printf '{"instances":%s}\n' "${ONTWIKKELPORTAAL_INSTANCES:-[]}" > /tmp/ontwikkelportaal-config.json

# security.txt (RFC 9116) at start: Expires may lie at most a year ahead, so a
# file baked into the image would go stale.
expires="$(date -u -d "@$(($(date +%s) + 365 * 24 * 3600))" +%Y-%m-%dT%H:%M:%SZ)"
cat > /tmp/ontwikkelportaal-security.txt <<EOF
# Proefomgeving van grip, geen productie. Deze site en de voorbeeldinstanties
# waar hij naar verwijst bevatten alleen verzonnen organisaties, personen en
# bedragen. Er draait hier geen dienst voor echt werk.
Contact: https://github.com/DigiGilde/grip/security/advisories/new
Policy: https://github.com/DigiGilde/grip/blob/main/SECURITY.md
Preferred-Languages: nl, en
Expires: $expires
EOF
