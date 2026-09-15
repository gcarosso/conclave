#!/usr/bin/env bash
# cockpit.sh — render <hub>/STATUS.md from live state.
# Read-only except for STATUS.md (plus a lock directory and a small attention-state file next to this script).
# Notifies (macOS osascript, or notify-send) only when the set of attention items changes; COCKPIT_NOTIFY=0 silences it.
set -uo pipefail
SYSTEM="$(cd "$(dirname "$0")/.." && pwd -P)"
HUB="$(python3 -c 'import json,os,sys
s=sys.argv[1]; h=None
try: h=json.load(open(os.path.join(s,"shared","governance.json"))).get("hub")
except Exception: pass
print(os.path.realpath(os.path.expanduser(h)) if h else os.path.dirname(s))' "$SYSTEM")"
SYSNAME="$(basename "$SYSTEM")"
OPS="$SYSTEM/ops"
LOCK="$OPS/.cockpit.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  # another render is running; if it is stale (>5 min) reclaim, else skip
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +5 2>/dev/null)" ]; then
    { rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" 2>/dev/null; } || exit 0
  else
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

OUT="$HUB/STATUS.md"
REG="$SYSTEM/registry/registry.json"
GOV="$SYSTEM/shared/governance.json"
POLICY="$SYSTEM/router/policy.json"
now=$(date '+%Y-%m-%d %H:%M %Z')
OPERATOR=$(python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get("operator") or "operator")
except Exception: print("operator")' "$GOV" 2>/dev/null || echo operator)
gov_present=0; [ -f "$GOV" ] && gov_present=1

# ---------------------------------------------------------------- body (everything after the attention block)
{
echo "## Scheduled jobs"
if [ -f "$REG" ]; then
  python3 - "$REG" <<'PY'
import json, subprocess, sys
r = json.load(open(sys.argv[1]))
ld = r.get("launchd") or {}
jobs = ld.get("jobs") or []
if ld.get("status") == "not-applicable":
    print("- launchd not applicable on this platform"); sys.exit()
if not jobs:
    pre = ld.get("prefixes") or []
    print("- none (%s)" % ("no LaunchAgents matched prefixes %s" % ", ".join(pre) if pre else ld.get("status") or "no prefixes configured")); sys.exit()
live = None
try:
    out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=20).stdout
    live = {}
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) == 3:
            live[p[2]] = p[1]
except Exception:
    live = None
print("| Job | Loaded | Last exit | Working dir |"); print("|---|---|---|---|")
for j in jobs:
    label = j.get("label", "?")
    if live is not None:
        loaded = "yes" if label in live else "NO"; ex = live.get(label, "?")
    else:
        loaded = "yes" if j.get("loaded") else "NO"; ex = j.get("last_exit") or "?"
    wd = "ok" if j.get("working_directory_exists") else "MISSING"
    print("| %s | %s | %s | %s |" % (label, loaded, ex, wd))
PY
else
  echo "- registry not generated — run \`make -C $SYSNAME/registry refresh\`"
fi
echo
echo "## Vendors"
if [ -f "$REG" ]; then
  python3 - "$REG" "$POLICY" "$GOV" <<'PY'
import json, sys
def load(p):
    try: return json.load(open(p))
    except Exception: return {}
r = load(sys.argv[1]); p = load(sys.argv[2]); g = load(sys.argv[3])
vendors = g.get("vendors") or list((p.get("ladders") or {}).keys()) or ["claude", "codex", "grok", "gemini"]
models = p.get("models") or (r.get("models") or {}).get("models") or []
def st(sec, key):
    return (((r.get(sec) or {}).get("probes") or {}).get(key) or {}).get("status", "?")
print("Registry generated %s." % r.get("generated", "?")); print()
print("| Vendor | Probe | Models |"); print("|---|---|---|")
for v in vendors:
    if v == "grok":
        probe = st("grok", "models")
    elif v == "gemini":
        key = (r.get("gemini") or {}).get("api_key", "?"); sdk = st("gemini", "sdk")
        probe = "ok" if (key == "set" and sdk == "ok") else "key %s, sdk %s" % (key, sdk)
    else:
        probe = st(v, "version")
    avail = [m["id"] for m in models if isinstance(m, dict) and m.get("vendor") == v and m.get("available")]
    print("| %s | %s | %s |" % (v, probe, ", ".join(avail) or "none"))
PY
else
  echo "- registry not generated — run \`make -C $SYSNAME/registry refresh\`"
fi
echo
echo "## Router health"
if [ -f "$SYSTEM/router/tests.py" ]; then
  echo "- tests: $(cd "$SYSTEM/router" && python3 tests.py 2>&1 | tail -1)"
else
  echo "- tests: router/tests.py missing"
fi
if [ "$gov_present" = 1 ]; then
  if [ -f "$SYSTEM/router/generate.py" ]; then
    drift=$(python3 "$SYSTEM/router/generate.py" --check 2>&1 | grep -E 'drifted' | tail -1)
    echo "- drift: ${drift:-check produced no summary line}"
  else
    echo "- drift: router/generate.py missing"
  fi
else
  echo "- drift: skipped (no shared/governance.json)"
fi
if [ -f "$SYSTEM/gate/tests/gate-test.sh" ]; then
  echo "- gate fixtures: $(bash "$SYSTEM/gate/tests/gate-test.sh" 2>/dev/null | tail -1)"
else
  echo "- gate fixtures: gate/tests/gate-test.sh missing"
fi
echo
echo "## Recent router jobs"
echo '```'
if [ -x "$SYSTEM/router/ai" ]; then
  jobs=$(cd "$HUB" && "$SYSTEM/router/ai" jobs 2>/dev/null | tail -8)
  echo "${jobs:-(no jobs recorded)}"
else
  echo "router/ai missing"
fi
echo '```'
echo
echo "## Public repos"
pub=$(python3 -c 'import json,sys
try: g=json.load(open(sys.argv[1]))
except Exception: sys.exit()
print("\n".join(sorted(k for k,v in (g.get("domains") or {}).items() if isinstance(v,dict) and v.get("kind")=="public")))' "$GOV" 2>/dev/null)
if [ "$gov_present" != 1 ]; then
  echo "- (no shared/governance.json — copy shared/governance.example.json)"
elif [ -z "$pub" ]; then
  echo "- (no public domains in governance)"
else
  found=0
  for dom in $pub; do
    ddir="$HUB/$dom"
    if [ ! -d "$ddir" ]; then echo "- $dom: directory missing"; continue; fi
    for d in "$ddir" "$ddir"/*/; do
      d="${d%/}"; [ -d "$d/.git" ] || continue
      found=1
      name="${d#"$HUB"/}"
      dirty=$(git -C "$d" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
      ahead=$(git -C "$d" rev-list --count '@{u}..HEAD' 2>/dev/null || echo '?')
      echo "- $name: dirty $dirty · ahead $ahead · $(git -C "$d" log -1 --format='%cd %s' --date=short 2>/dev/null | cut -c1-60)"
    done
  done
  [ "$found" = 1 ] || echo "- (no git repositories under public domains)"
fi
echo
echo "## Open for $OPERATOR"
if [ -s "$SYSTEM/OPEN.md" ]; then cat "$SYSTEM/OPEN.md"; else echo "- (none listed; edit $SYSNAME/OPEN.md)"; fi
} > "$OUT.tmp"

# ---------------------------------------------------------------- attention: derived from the rendered facts
ATT=$(python3 - "$OUT.tmp" "$gov_present" "$SYSNAME" <<'PY'
import os, re, sys
t = open(sys.argv[1], encoding="utf-8").read(); gov = sys.argv[2] == "1"; sysname = sys.argv[3]
secs = {}; cur = None
for line in t.splitlines():
    if line.startswith("## "):
        cur = line[3:].strip(); secs[cur] = []
    elif cur is not None:
        secs[cur].append(line)
def sec(n): return "\n".join(secs.get(n, []))
a = []
if not gov: a.append("shared/governance.json missing — copy shared/governance.example.json")
if "registry not generated" in t: a.append("registry not generated — run make -C %s/registry refresh" % sysname)
for m in re.finditer(r'^\| (\S+) \| (yes|NO) \| (\S+) \| (\S+) \|$', sec("Scheduled jobs"), re.M):
    job, loaded, ex, wd = m.groups()
    if loaded != "yes": a.append("%s not loaded" % job)
    elif ex not in ("0", "?", "-"): a.append("%s last exit %s" % (job, ex))
    if wd == "MISSING": a.append("%s working directory missing" % job)
for m in re.finditer(r'^\| (\S+) \| ([^|]*?) \| ', sec("Vendors"), re.M):
    v, st = m.group(1), m.group(2).strip()
    if v == "Vendor": continue
    if st != "ok": a.append("vendor probe %s: %s" % (v, st))
h = sec("Router health")
if not re.search(r'^- tests: OK', h, re.M): a.append("router tests failing")
d = re.search(r'^- drift: (.*)$', h, re.M); d = d.group(1) if d else ""
if not d.startswith("skipped") and "0 drifted" not in d: a.append("governance drift — run make -C %s/router generate" % sysname)
g = re.search(r'^- gate fixtures: (.*)$', h, re.M); g = g.group(1) if g else ""
if "0 failed" not in g: a.append("publish-gate fixtures failing" if "failed" in g else "publish-gate fixtures: %s" % (g or "no result"))
for m in re.finditer(r'^(fail|blocked)\s+(\S+)\s+(\S+)\s+(\S+)', sec("Recent router jobs"), re.M):
    a.append("job %s: %s in %s (%s)" % (m.group(1), m.group(3), m.group(2), os.path.basename(m.group(4))))
for m in re.finditer(r'^- (\S+): dirty (\d+) · ahead (\d+)', sec("Public repos"), re.M):
    if int(m.group(3)) > 0: a.append("%s: %s unpushed commit(s)" % (m.group(1), m.group(3)))
print("\n".join(a))
PY
)

# ---------------------------------------------------------------- assemble STATUS.md
{
  echo "# Cockpit — $now"
  echo "Refresh: \`make -C $SYSNAME/ops cockpit\` · Rules agents read: \`CROSS-DOMAIN.md\`"
  echo
  if [ -n "$ATT" ]; then echo "## ⚠ Attention"; echo "$ATT" | sed 's/^/- /'; else echo "## ✓ Nothing needs you"; fi
  echo
  cat "$OUT.tmp"
} > "$OUT"
rm -f "$OUT.tmp"

# ---------------------------------------------------------------- notify only when the attention set changes
notify() { # $1 title, $2 body
  [ "${COCKPIT_NOTIFY:-1}" = "0" ] && return 0
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'on run argv' -e 'display notification (item 2 of argv) with title (item 1 of argv)' -e 'end run' "$1" "$2" >/dev/null 2>&1 || true
  elif command -v notify-send >/dev/null 2>&1; then
    notify-send "$1" "$2" >/dev/null 2>&1 || true
  fi
}
STATE="$OPS/.cockpit-attention"; prev=$(cat "$STATE" 2>/dev/null || true)
if [ "$ATT" != "$prev" ]; then
  printf '%s' "$ATT" > "$STATE"
  if [ -n "$ATT" ]; then
    n=$(echo "$ATT" | grep -c .); first=$(echo "$ATT" | head -1 | cut -c1-90)
    notify "Cockpit: $n item(s) need attention" "$first"
  else
    notify "Cockpit" "All clear"
  fi
fi
echo "wrote $OUT ($(echo "$ATT" | grep -c .) attention items)"
