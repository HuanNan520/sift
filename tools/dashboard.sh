#!/usr/bin/env bash
# Sift vault health dashboard — single-page HTML report.
#
# Usage:
#   ./tools/dashboard.sh [vault-path] [--out FILE] [--title "..."]
#   ./tools/dashboard.sh ~/my-vault > dashboard.html
#   ./tools/dashboard.sh ~/my-vault --out report.html
#
# Output is zero-dependency HTML — inline SVG + CSS, no CDN, no JS framework.
# Open in any browser; ship via `cp` or `scp`.
#
# Requires: python3, pyyaml.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/dashboard.py" "$@"
