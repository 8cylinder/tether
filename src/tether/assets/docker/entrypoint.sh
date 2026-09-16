#!/usr/bin/env bash
set -euo pipefail

# Use a consistent home directory so host-mounted config (e.g. ~/.claude)
# lands at a known path regardless of --user or platform.
export HOME="/tmp/tether-home"
mkdir -p "${HOME}/.config" "${HOME}/.cache" 2>/dev/null || true

if [[ "$#" -eq 0 ]]; then
  set -- bash
fi

exec "$@"
