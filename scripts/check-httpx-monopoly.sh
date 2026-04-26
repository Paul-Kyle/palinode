#!/bin/bash
# check-httpx-monopoly.sh — enforce ADR-010 HTTP-layer monopoly.
#
# Per ADR-010 (Cross-Surface Parity Contract), every CLI command and the
# plugin must reach the API through one of two HTTP clients:
#
#   - palinode/cli/_api.py  (CLI → API)
#   - palinode/mcp.py       (MCP → API)
#
# Direct `httpx` calls from any other source file silently bypass rate
# limiting, audit logging, the X-Palinode-Source header, and any future
# API-side fixes.  Each bypass is a parity-rot vector.  We block them at
# pre-commit / CI time.
#
# Usage:
#   ./scripts/check-httpx-monopoly.sh                 # scan whole tree
#   ./scripts/check-httpx-monopoly.sh --diff <ref>    # scan files changed vs <ref>
#   ./scripts/check-httpx-monopoly.sh path/to/file [...] # specific files
#
# Exit code: 0 = clean, 1 = bypass found.
#
# The known-grandfathered bypass list is encoded below.  Cleaning these is
# tracked in #168 and the lower-tier of #170; until that work lands the
# script reports them but does not fail.  Any *new* bypass fails.

set -euo pipefail

# Scope: CLI files (`palinode/cli/*.py`) talking to the Palinode API.
# Outbound HTTP to *other* services (Ollama, source URLs, mem0/migration
# endpoints) is unrelated to ADR-010 and lives in core/ingest/migration/
# consolidation/api modules — we don't scan those.
SCAN_GLOBS=(
    "palinode/cli/*.py"
)

# Within SCAN_GLOBS, this file is the canonical HTTP client.
ALLOWED_FILES=(
    "palinode/cli/_api.py"
)

# Files known to violate today.  Tracked for cleanup; allowed for now.
# When the cleanup PR lands, remove the file from this list — the script then
# fails if the bypass returns.
#
# As of the lower-tier #170 cleanup the list is empty: list/lint/prompt/
# ingest/session_end have all moved to PalinodeAPI in palinode/cli/_api.py.
# The historical disk-read bypass in cli/read.py was closed earlier in #168
# (it now goes through `api_client.read()`).  Any *new* bypass fails.
GRANDFATHERED=(
)

# Determine scan set
mode="all"
files=()
if [[ "${1:-}" == "--diff" ]]; then
    mode="diff"
    base="${2:-origin/main}"
    while IFS= read -r f; do
        [[ -n "$f" ]] && files+=("$f")
    done < <(git diff --name-only --diff-filter=AM "$base" -- 'palinode/**/*.py' 'plugin/**/*.ts' 2>/dev/null || true)
elif [[ $# -gt 0 ]]; then
    mode="specific"
    files=("$@")
else
    for glob in "${SCAN_GLOBS[@]}"; do
        while IFS= read -r f; do
            [[ -n "$f" ]] && files+=("$f")
        done < <(compgen -G "$glob" 2>/dev/null || true)
    done
fi

if [[ ${#files[@]} -eq 0 ]]; then
    echo "check-httpx-monopoly: no files to scan ($mode mode)"
    exit 0
fi

is_allowed() {
    local f="$1"
    for a in "${ALLOWED_FILES[@]}"; do
        [[ "$f" == "$a" || "$f" == */"$a" ]] && return 0
    done
    return 1
}

is_grandfathered() {
    local f="$1"
    for g in "${GRANDFATHERED[@]}"; do
        [[ "$f" == "$g" || "$f" == */"$g" ]] && return 0
    done
    return 1
}

violations=0
warnings=0

for f in "${files[@]}"; do
    [[ -f "$f" ]] || continue
    is_allowed "$f" && continue

    # Look for raw httpx use.  ``import httpx`` and ``httpx.<method>`` calls
    # are the bypass markers.  We allow ``import httpx`` only if it's used
    # for type hints (``httpx.Response``, ``httpx.Client``) without instance
    # creation — but that's hard to grep cleanly, so we report the import
    # and let the reviewer judge.  In practice every today-bypass file does
    # actual HTTP calls; the conservative default is to flag.
    if grep -qE '^[[:space:]]*import[[:space:]]+httpx|^[[:space:]]*from[[:space:]]+httpx[[:space:]]+import|httpx\.(get|post|put|delete|patch|request|Client|AsyncClient)' "$f"; then
        if is_grandfathered "$f"; then
            echo "warn: $f uses httpx directly (grandfathered, see ADR-010 / #170)"
            warnings=$((warnings + 1))
        else
            echo "fail: $f uses httpx directly — go through palinode/cli/_api.py or palinode/mcp.py"
            violations=$((violations + 1))
        fi
    fi
done

if [[ $violations -gt 0 ]]; then
    echo
    echo "ADR-010 (HTTP-layer monopoly) violation: $violations file(s) bypass the API client."
    echo "If a new bypass is intentional, document the carve-out in docs/PARITY.md and update this script."
    exit 1
fi

if [[ $warnings -gt 0 ]]; then
    echo
    echo "$warnings grandfathered bypass(es) noted (cleanup tracked in #170)."
fi

exit 0
