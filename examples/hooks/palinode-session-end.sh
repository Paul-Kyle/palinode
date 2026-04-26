#!/bin/bash
# palinode-session-end.sh — Auto-capture Claude Code sessions to Palinode.
#
# Fires on SessionEnd (including /clear, logout, exit). Reads the transcript
# from stdin JSON, extracts a minimal summary, and POSTs to palinode-api.
#
# Fail-silent by design — never block Claude Code exit. If the API is down
# we drop the capture and move on. Nightly consolidation will pick up the
# snapshot on the next pass.
#
# Install:
#   1. Copy to .claude/hooks/palinode-session-end.sh (or ~/.claude/hooks/…)
#   2. chmod +x .claude/hooks/palinode-session-end.sh
#   3. Register in .claude/settings.json — see ./settings.json in this dir.
#
# Or just run: `palinode init` — it installs all of this for you.

set -euo pipefail

PALINODE_API="${PALINODE_API_URL:-http://localhost:6340}"
MIN_MESSAGES="${PALINODE_HOOK_MIN_MESSAGES:-3}"

# Reasons to capture on. Default broad: clear, logout, normal exit (other),
# and non-interactive EOF. Override with PALINODE_HOOK_REASONS to narrow
# (e.g. "clear") or extend (add "resume" / "bypass_permissions_disabled").
# See https://code.claude.com/docs/en/hooks.md for the full reason list.
ALLOWED_REASONS="${PALINODE_HOOK_REASONS:-clear logout prompt_input_exit other}"

INPUT=$(cat)
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
SOURCE_REASON=$(echo "$INPUT" | jq -r '.source // .reason // "other"')

# Drop reasons we're not capturing. Word-boundary match on a space-padded
# allowlist so substrings (e.g. "log" in "logout") don't false-positive.
case " $ALLOWED_REASONS " in
  *" $SOURCE_REASON "*) ;;
  *) exit 0 ;;
esac

# No transcript → nothing to capture.
if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

# Claude Code transcript format (JSONL):
#   user:      {type: "user", message: {role: "user", content: "text"}}
#   assistant: {type: "assistant", message: {content: [{type: "text", text: "..."}]}}
#
# `grep -c '.'` always prints a single integer (even "0") regardless of exit
# code — so we rely on its output and use `|| true` to swallow the non-zero
# exit that fires when no lines match. The trailing `:-0` is a final safety
# in case the pipeline produces no stdout at all (e.g. transcript vanished).
# Without these guards the prior code emitted "0\n0" on empty transcripts,
# which broke the integer test below and let bogus captures through (#151).
MSG_COUNT=$(jq -r 'select(.type == "user") | .message.content // empty' \
  "$TRANSCRIPT_PATH" 2>/dev/null | grep -c '.' || true)
MSG_COUNT=${MSG_COUNT:-0}

# Skip trivial sessions (few messages = not worth a memory).
if [ "$MSG_COUNT" -lt "$MIN_MESSAGES" ]; then
  exit 0
fi

PROJECT=$(basename "$CWD" 2>/dev/null || echo "unknown")
FIRST_PROMPT=$(jq -r 'select(.type == "user") | .message.content // empty' \
  "$TRANSCRIPT_PATH" 2>/dev/null | head -1 | cut -c1-200)

SUMMARY="Auto-captured (${SOURCE_REASON}, ${MSG_COUNT} messages). Topic: ${FIRST_PROMPT}"

curl -sS -o /dev/null \
  -X POST "${PALINODE_API}/session-end" \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
    --arg summary "$SUMMARY" \
    --arg project "$PROJECT" \
    --arg source "claude-code-hook" \
    '{summary: $summary, project: $project, source: $source, decisions: [], blockers: []}'
  )" \
  --connect-timeout 5 \
  --max-time 10 || true

exit 0
