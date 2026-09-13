#!/usr/bin/env bash
set -euo pipefail

# The container may run with an arbitrary uid (the host user) whose home
# directory is not writable. Fall back to an ephemeral home in that case.
if [[ -z "${HOME:-}" || ! -w "${HOME}" ]]; then
  export HOME="/tmp/tether-home"
fi
mkdir -p "${HOME}/.config" "${HOME}/.cache" 2>/dev/null || true

if [[ "$#" -eq 0 ]]; then
  set -- bash
fi

exec "$@"
