#!/usr/bin/env bash
# Sift vault recheck — report cards near or past expiration.
#
# Usage:
#   ./tools/recheck.sh [vault-path] [--within-days N] [--include-scripts] [--json]
#   ./tools/recheck.sh                            # scan cwd, default 30-day window
#   ./tools/recheck.sh ~/my-vault                 # scan another vault
#   ./tools/recheck.sh ~/my-vault --within-days 60
#   ./tools/recheck.sh ~/my-vault --json          # for dashboards / CI
#
# Exits non-zero if any card is expired or near expiration. Useful in
# cron / pre-commit hooks / scheduled scripts.
#
# Requires: python3, pyyaml
#   pip install pyyaml       # or use a venv

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/recheck.py" "$@"
