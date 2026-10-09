#!/usr/bin/env bash
# Render the chart and check that the JWT secret placeholder is rejected.
set -euo pipefail

chart="$(dirname "$0")/consentos"

expect_failure() {
  local description="$1"; shift
  local output
  if output="$(helm template test "$chart" "$@" 2>&1)"; then
    echo "FAIL: $description rendered but should have been rejected"
    exit 1
  fi
  if ! grep -q "secrets.jwtSecretKey must be set" <<<"$output"; then
    echo "FAIL: $description failed for an unexpected reason:"
    echo "$output"
    exit 1
  fi
  echo "ok: $description is rejected"
}

expect_success() {
  local description="$1"; shift
  helm template test "$chart" "$@" >/dev/null
  echo "ok: $description renders"
}

expect_failure "default values"
expect_failure "empty jwtSecretKey" --set secrets.jwtSecretKey=
expect_success "random jwtSecretKey" --set secrets.jwtSecretKey="$(openssl rand -hex 32)"
expect_success "existingSecret" --set secrets.existingSecret=my-secret
