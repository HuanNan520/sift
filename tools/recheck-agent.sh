#!/usr/bin/env bash
# Sift vault recheck agent — AI-driven kill / merge / rewrite via LLM.
#
# Usage:
#   ./tools/recheck-agent.sh [--dry-run] [--week YYYY-Www] [--category C]
#   ./tools/recheck-agent.sh --dry-run                       # don't touch files
#   ./tools/recheck-agent.sh --category debug --dry-run      # one category
#   ./tools/recheck-agent.sh                                 # real soft-delete + report
#
# Outputs week report to ~/claude-journal/sift/_reports/YYYY-WW.md
# Soft deletes kills to ~/claude-journal/skills/_trash/YYYY-WW/
# Sends Telegram summary if TG_BOT_TOKEN + TG_CHAT_ID env set.
#
# Note: this is the LLM-driven recheck agent. The simpler `recheck.sh` is
# the rule-based expires field check.
#
# Requires: python3 (stdlib only).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/recheck-agent.py" "$@"
