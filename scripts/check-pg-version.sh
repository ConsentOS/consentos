#!/usr/bin/env bash
# Fail-fast Postgres major-version check.
#
# Reads PG_VERSION from the on-disk Postgres data volume (if any) and
# compares it to the major version declared by the postgres image in
# docker-compose.yml. Exits 1 with a pointer to the README upgrade
# section when they diverge, so operators see a clear error before
# the postgres container hits the cryptic:
#
#   FATAL: database files are incompatible with server
#
# Override the volume name via POSTGRES_VOLUME for tests / non-default
# project names.

set -euo pipefail

VOLUME=${POSTGRES_VOLUME:-consentos_pgdata}
EXPECTED=$(grep -m1 -oE 'image:[[:space:]]+postgres:[0-9]+' docker-compose.yml 2>/dev/null | sed -E 's/.*postgres:([0-9]+).*/\1/')

if [ -z "$EXPECTED" ]; then
  echo "check-pg-version: could not parse postgres major version from docker-compose.yml" >&2
  exit 0
fi

if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  exit 0
fi

ON_DISK=$(docker run --rm -v "${VOLUME}:/data" alpine:3 sh -c 'cat /data/PG_VERSION 2>/dev/null || true')
ON_DISK=$(echo "$ON_DISK" | tr -d '[:space:]')

if [ -z "$ON_DISK" ]; then
  exit 0
fi

if [ "$ON_DISK" != "$EXPECTED" ]; then
  cat >&2 <<EOF

Postgres major-version mismatch:
  on-disk volume "${VOLUME}":   PG${ON_DISK}
  docker-compose.yml image:     PG${EXPECTED}

The postgres container will fail to start with "database files are
incompatible with server". See "Upgrading from PostgreSQL ${ON_DISK}"
in README.md for two recovery paths (nuke-and-reseed or
dump-and-restore).

EOF
  exit 1
fi
