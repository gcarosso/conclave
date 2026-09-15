#!/usr/bin/env bash
# handoff-to-vendor.sh — hand the coordinator role to another vendor's CLI (e.g. when the current one is rate-limited).
# Writes a session handoff, appends a "Coordinator handoff" block, then prints the exact command to run.
#   handoff-to-vendor.sh [--approve-top-model] <claude|codex> "next task"
# The model is the tier-3 entry of that vendor's ladder in router/policy.json; the approval line names the
# operator from shared/governance.json.
set -euo pipefail
SYSTEM="$(cd "$(dirname "$0")/.." && pwd -P)"
HUB="$(python3 -c 'import json,os,sys
s=sys.argv[1]; h=None
try: h=json.load(open(os.path.join(s,"shared","governance.json"))).get("hub")
except Exception: pass
print(os.path.realpath(os.path.expanduser(h)) if h else os.path.dirname(s))' "$SYSTEM")"
SYSNAME="$(basename "$SYSTEM")"
GOV="$SYSTEM/shared/governance.json"
POLICY="$SYSTEM/router/policy.json"

APPROVED=0
if [ "${1:-}" = "--approve-top-model" ]; then APPROVED=1; shift; fi
VENDOR="${1:-}"
TASK="${2:-Continue the open items in $SYSNAME/OPEN.md.}"
case "$VENDOR" in
  claude|codex) ;;
  *) echo "usage: $(basename "$0") <claude|codex> \"one-line task\"" >&2; exit 2;;
esac

MODEL=$(python3 -c 'import json,sys
try: print((json.load(open(sys.argv[1])).get("ladders") or {}).get(sys.argv[2], {}).get("3", ""))
except Exception: print("")' "$POLICY" "$VENDOR")
if [ -z "$MODEL" ]; then
  echo "no tier-3 model for '$VENDOR' in $SYSNAME/router/policy.json ladders" >&2; exit 1
fi
OPERATOR=$(python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get("operator") or "operator")
except Exception: print("operator")' "$GOV")

GATED=$(python3 -c 'import json,sys
p=json.load(open(sys.argv[1])); m=next((m for m in p["models"] if m["id"]==sys.argv[2]), None)
if not m or not m.get("available") or m["vendor"] != sys.argv[3]: sys.exit("model unavailable or mismatched")
print("yes" if m.get("requires_approval") else "no")' "$POLICY" "$MODEL" "$VENDOR")
if [ "$GATED" = yes ] && [ "$APPROVED" != 1 ]; then
  echo "$MODEL requires explicit approval: pass --approve-top-model to prepare this handoff." >&2
  exit 2
fi
APPROVAL_NOTE="No approval required by policy for $MODEL."
if [ "$GATED" = yes ]; then APPROVAL_NOTE="$OPERATOR supplied --approve-top-model for $MODEL for this handoff."; fi
H="$SYSTEM/handoffs"; mkdir -p "$H"
TS=$(date -u +%Y%m%dT%H%M%SZ); F="$H/$TS-handoff.md"
bash "$SYSTEM/ops/session-handoff.sh" --output "$F" --task "$TASK" >/dev/null

if [ "$VENDOR" = codex ]; then READ_FIRST="AGENTS.md"; else READ_FIRST="CLAUDE.md"; fi
cat >> "$F" <<EOF

## Coordinator handoff → $VENDOR ($MODEL), $TS
**Task from $OPERATOR:** $TASK
**Read first:** $READ_FIRST (hub root), CROSS-DOMAIN.md, STATUS.md, $SYSNAME/OPEN.md, $SYSNAME/coordination/PROTOCOL.md.
**Rules that bind you here:** one writer per file set · archive, never delete · exit 0 ≠ acceptance (run jobs through \`$SYSNAME/router/ai\`) · publication only via \`$SYSNAME/gate/publish-gate.sh\` · top-model approvals are recorded in the job contract.
**Approval:** $APPROVAL_NOTE
EOF

PROMPT="Read $F and carry out the task it names. Report what you changed and what remains."
REPORT="$H/$TS-$VENDOR-report.md"
echo "handoff: $F"
echo
echo "Run this (hub root, $MODEL as coordinator):"
case "$VENDOR" in
  codex)
    printf '  cd %q && codex -m %q -s workspace-write --skip-git-repo-check %q\n' "$HUB" "$MODEL" "$PROMPT"
    echo
    echo "Headless instead:"
    printf '  cd %q && codex exec -m %q -s workspace-write --skip-git-repo-check -o %q %q < /dev/null\n' "$HUB" "$MODEL" "$REPORT" "$PROMPT"
    ;;
  claude)
    printf '  cd %q && claude --model %q %q\n' "$HUB" "$MODEL" "$PROMPT"
    echo
    echo "Headless instead:"
    printf '  cd %q && claude -p --model %q %q > %q < /dev/null\n' "$HUB" "$MODEL" "$PROMPT" "$REPORT"
    ;;
esac
