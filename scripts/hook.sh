#!/bin/bash
# Agentarium hook for Claude Code
# Forwards hook events to Agentarium API
#
# Installation:
#   1. Run: python scripts/setup.py
#   2. Or manually copy to ~/.agentarium/hook.sh and update Claude settings
#
# Usage:
#   Claude Code automatically pipes event JSON to stdin when hooks fire

AGENTARIUM_URL="${AGENTARIUM_URL:-http://localhost:8000}"

# Read JSON from stdin (Claude Code pipes event data)
EVENT_JSON=$(cat)

# Forward to Agentarium API (run in background to not block Claude)
curl -s -X POST "${AGENTARIUM_URL}/api/events" \
  -H "Content-Type: application/json" \
  -d "$EVENT_JSON" > /dev/null 2>&1 &
