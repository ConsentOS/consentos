#!/usr/bin/env bash
# Smoke test for scripts/check-pg-version.sh. Creates throwaway docker
# volumes containing different PG_VERSION files, runs the check, and
# asserts the exit code matches expectations. Requires docker.

set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPT="$HERE/check-pg-version.sh"
ROOT=$(cd "$HERE/.." && pwd)

fail=0

run_case() {
  local label=$1 version=$2 expect_exit=$3
  local vol="cpv-test-$$-$RANDOM"

  docker volume create "$vol" >/dev/null
  if [ -n "$version" ]; then
    docker run --rm -v "${vol}:/data" alpine:3 sh -c "echo $version > /data/PG_VERSION"
  fi

  set +e
  ( cd "$ROOT" && POSTGRES_VOLUME="$vol" "$SCRIPT" >/dev/null 2>&1 )
  local actual=$?
  set -e

  docker volume rm "$vol" >/dev/null

  if [ "$actual" -eq "$expect_exit" ]; then
    printf '  ok   %-32s exit=%s\n' "$label" "$actual"
  else
    printf '  FAIL %-32s exit=%s (expected %s)\n' "$label" "$actual" "$expect_exit"
    fail=1
  fi
}

EXPECTED_MAJOR=$(grep -m1 -oE 'image:[[:space:]]+postgres:[0-9]+' "$ROOT/docker-compose.yml" | sed -E 's/.*postgres:([0-9]+).*/\1/')

echo "check-pg-version smoke tests (compose declares PG${EXPECTED_MAJOR}):"
run_case "matching major version"      "$EXPECTED_MAJOR" 0
run_case "older major version (PG16)"  "16"              1
run_case "future major version (PG18)" "18"              1
run_case "volume with no PG_VERSION"   ""                0

# Volume missing entirely
set +e
( cd "$ROOT" && POSTGRES_VOLUME="cpv-nonexistent-$$" "$SCRIPT" >/dev/null 2>&1 )
actual=$?
set -e
if [ "$actual" -eq 0 ]; then
  printf '  ok   %-32s exit=%s\n' "volume does not exist" "$actual"
else
  printf '  FAIL %-32s exit=%s (expected 0)\n' "volume does not exist" "$actual"
  fail=1
fi

exit "$fail"
