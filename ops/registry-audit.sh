#!/usr/bin/env bash
# registry-audit.sh — snapshot → regenerate → diff → flag.
# Exit code = number of issues (0 = clean, capped at 98; 99 = generator failed). Keeps the last 10 snapshots.
set -uo pipefail
SYSTEM="$(cd "$(dirname "$0")/.." && pwd -P)"
REG_DIR="$SYSTEM/registry"
SNAP="$REG_DIR/snapshots"; mkdir -p "$SNAP"
TS=$(date -u +%Y%m%dT%H%M%SZ)
[ -f "$REG_DIR/registry.json" ] && cp "$REG_DIR/registry.json" "$SNAP/registry-$TS.json"

echo "=== Registry audit $TS ==="
python3 "$REG_DIR/generate.py" || { echo "generator failed"; exit 99; }

python3 - "$REG_DIR/registry.json" "$SNAP" <<'EOF'
import glob, json, os, sys
reg = json.load(open(sys.argv[1])); snap = sys.argv[2]
OK = (None, "ok", "skipped", "not-applicable")
issues = []
for k in ("claude", "codex", "grok", "gemini", "composio", "launchd", "extra", "models"):
    sec = reg.get(k) or {}
    for name, p in (sec.get("probes") or {}).items():
        if isinstance(p, dict) and p.get("status") not in OK:
            issues.append("%s probe '%s': %s %s" % (k, name, p.get("status"), (p.get("stderr") or "")[:120]))
for j in (reg.get("launchd") or {}).get("jobs") or []:
    if not j.get("loaded"): issues.append("launchd %s NOT LOADED" % j.get("label"))
    if not j.get("working_directory_exists"): issues.append("launchd %s working directory missing: %s" % (j.get("label"), j.get("working_directory")))
    if j.get("last_exit") not in (None, "0", "-"): issues.append("launchd %s last exit %s" % (j.get("label"), j.get("last_exit")))
for c in (reg.get("composio") or {}).get("connections") or []:
    if c.get("status") != "ACTIVE": issues.append("composio %s (%s) %s" % (c.get("app"), c.get("id"), c.get("status")))
if (reg.get("manual") or {}).get("status") == "error":
    issues.append("manual.json unreadable: %s" % (reg["manual"].get("stderr") or "")[:120])
if (reg.get("config") or {}).get("status") == "error":
    issues.append("config.json unreadable: %s" % (reg["config"].get("stderr") or "")[:120])
# diff against the newest snapshot (= the registry as it was before this regeneration)
prev = sorted(glob.glob(os.path.join(snap, "registry-*.json")))
if prev:
    try: old = json.load(open(prev[-1]))
    except Exception: old = {}
    def names(sec, key):
        return {m["name"] if isinstance(m, dict) else m for m in ((sec or {}).get(key) or [])}
    for k, key in (("claude", "mcp"), ("claude", "skills"), ("claude", "agents"), ("codex", "mcp"), ("codex", "agents"), ("grok", "models")):
        a, b = names(old.get(k), key), names(reg.get(k), key)
        if a != b: print("changed %s.%s: -%s +%s" % (k, key, sorted(a - b), sorted(b - a)))
for i in issues: print("⚠  " + i)
print("=== %d issue(s) ===" % len(issues))
sys.exit(min(len(issues), 98))
EOF
rc=$?
ls -1t "$SNAP"/registry-*.json 2>/dev/null | tail -n +11 | while IFS= read -r old; do rm -f "$old"; done
exit "$rc"
