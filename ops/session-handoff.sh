#!/usr/bin/env bash
# session-handoff.sh — write a context-transfer document for the next session (any vendor).
# Usage: session-handoff.sh [--output FILE] [--task "description"] [--session-id ID]
# Default output: <checkout>/handoffs/<UTC timestamp>-handoff.md
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
INDEX="$SYSTEM/router/jobs/index.jsonl"
HANDOFF_DIR="$SYSTEM/handoffs"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTPUT=""; SESSION_ID=""; TASK_DESC=""

usage() { sed -n '2,4p' "$0" | sed 's/^# //'; }
while [ $# -gt 0 ]; do
  case "$1" in
    --output|-o)     OUTPUT="${2:?--output needs a file}"; shift 2;;
    --session-id|-s) SESSION_ID="${2:?--session-id needs a value}"; shift 2;;
    --task|-t)       TASK_DESC="${2:?--task needs a description}"; shift 2;;
    -h|--help)       usage; exit 0;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2;;
  esac
done

mkdir -p "$HANDOFF_DIR"
[ -n "$OUTPUT" ] || OUTPUT="$HANDOFF_DIR/${TIMESTAMP}-handoff.md"

public_domains() {
  python3 -c 'import json,sys
try: g=json.load(open(sys.argv[1]))
except Exception: sys.exit()
print("\n".join(sorted(k for k,v in (g.get("domains") or {}).items() if isinstance(v,dict) and v.get("kind")=="public")))' "$GOV" 2>/dev/null || true
}

{
echo "# Session Handoff — $TIMESTAMP"
if [ -n "$SESSION_ID" ]; then echo "Session: $SESSION_ID"; fi
echo
echo "## Pending Task"
echo "${TASK_DESC:-(none given — pass --task \"...\")}"
echo
echo "## Workspace State"
echo "Hub: \`$HUB\` · control plane: \`$SYSNAME/\`"
echo
echo "### Domains"
python3 - "$GOV" "$HUB" <<'PY'
import json, os, sys
try:
    g = json.load(open(sys.argv[1]))
except FileNotFoundError:
    print("- (no shared/governance.json — copy shared/governance.example.json)"); sys.exit()
except Exception as e:
    print("- (governance unreadable: %s)" % e); sys.exit()
hub = sys.argv[2]
doms = g.get("domains") or {}
if not doms: print("- (no domains in governance)")
for name, d in sorted(doms.items()):
    kind = d.get("kind", "?") if isinstance(d, dict) else "?"
    p = os.path.join(hub, name)
    if not os.path.isdir(p):
        print("- `%s/` [%s] (missing)" % (name, kind)); continue
    n = sum(len(fs) for _, _, fs in os.walk(p))
    print("- `%s/` [%s] (%d files)" % (name, kind, n))
PY
echo
echo "### Router"
vendors=$(python3 -c 'import json,sys
try: print(", ".join(json.load(open(sys.argv[1])).get("vendors") or []) or "(none listed)")
except FileNotFoundError: print("(no shared/governance.json)")
except Exception: print("(governance unreadable)")' "$GOV" 2>/dev/null || echo "?")
roles=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("roles") or {}))' "$POLICY" 2>/dev/null || echo "?")
echo "- Vendors (governance): $vendors"
echo "- Roles (policy): $roles defined"
echo
echo "### Recent Router Jobs (last 5)"
if [ -f "$INDEX" ]; then
  python3 - "$INDEX" <<'PY'
import json, os, sys
rows = []
for line in open(sys.argv[1]):
    line = line.strip()
    if not line: continue
    try: rows.append(json.loads(line))
    except Exception: continue
rows = rows[-5:]
if not rows: print("- (index empty)")
for j in rows:
    jd = j.get("job_dir") or ""
    try:
        st = json.load(open(os.path.join(jd, "acceptance.json"))).get("acceptance_status") or "?"
    except Exception:
        st = "?"
    print("- `%s` %s/%s → %s" % (j.get("id", "?"), j.get("domain", "?"), j.get("role", "?"), st))
PY
else
  echo "- (no jobs index at $SYSNAME/router/jobs/index.jsonl)"
fi
echo
echo "### Git Status (public-domain repos)"
found=0
for dom in $(public_domains); do
  ddir="$HUB/$dom"
  [ -d "$ddir" ] || { echo "- \`$dom\`: directory missing"; continue; }
  for d in "$ddir" "$ddir"/*/; do
    d="${d%/}"; [ -d "$d/.git" ] || continue
    found=1
    name="${d#"$HUB"/}"
    branch=$(git -C "$d" branch --show-current 2>/dev/null || echo "?")
    dirty=$(git -C "$d" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    ahead=$(git -C "$d" rev-list --count '@{u}..HEAD' 2>/dev/null || echo "?")
    echo "- \`$name\`: branch=${branch:-?}, dirty=$dirty, ahead=$ahead"
  done
done
[ "$found" = 1 ] || echo "- (none)"
echo
echo "### Key Files"
echo "- Router: \`$SYSNAME/router/ai\`"
echo "- Policy: \`$SYSNAME/router/policy.json\`"
echo "- Governance: \`$SYSNAME/shared/governance.json\`"
echo "- Registry: \`$SYSNAME/registry/REGISTRY.md\`"
echo "- Ops scripts: \`$SYSNAME/ops/\`"
echo "- Coordination: \`$SYSNAME/coordination/\`"
echo
echo "### Environment"
echo "- OS: $(uname -s) $(sw_vers -productVersion 2>/dev/null || uname -r)"
echo "- Python $(python3 --version 2>/dev/null | awk '{print $2}' || echo '?')"
echo "- Node $(node --version 2>/dev/null || echo 'not found')"
echo "- GEMINI_API_KEY: $([ -n "${GEMINI_API_KEY:-}" ] && echo set || echo unset)"
echo
echo "---"
echo "Generated: $TIMESTAMP"
} > "$OUTPUT"
echo "Handoff written to: $OUTPUT"
