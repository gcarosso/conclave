#!/usr/bin/env bash
# End-to-end check: build a throwaway hub around a copy of this checkout and drive the real `ai` CLI.
#
#   scripts/e2e.sh            offline: fake `claude` and `codex` CLIs on PATH (scripts/fake-vendors/)
#   scripts/e2e.sh --live     one real tier-1 scout job through the vendors you are logged into (costs a call)
#   scripts/e2e.sh --keep     keep the temporary hub and print its path
#
# Covers: install.sh --init, generated files and drift check, dry runs, a vendor refused by data class,
# a scout job, a write job whose first draft the reviewer rejects (repair path), ai accept, ai jobs,
# council and consensus dry runs, cockpit, session and vendor handoffs, gate hooks on a public repo
# (clean commit passes, a planted key is blocked), registry probe, and the docs link check.
# Exit status is the number of failed steps. Nothing outside the temporary directory is written.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
LIVE=0; KEEP=0
for a in "$@"; do
  case "$a" in
    --live) LIVE=1 ;;
    --keep) KEEP=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $a"; exit 2 ;;
  esac
done

T="$(mktemp -d "${TMPDIR:-/tmp}/conclave-e2e.XXXXXX")"
T="$(cd "$T" && pwd -P)"
if [ "$KEEP" = 1 ]; then trap 'echo "kept: $T"' EXIT; else trap 'rm -rf "$T"' EXIT; fi
HUB="$T/hub"; SYS="$HUB/_system"; AI="$T/prefix/bin/ai"; LOG="$T/log"
mkdir -p "$SYS" "$T/state"
export AI_NO_COCKPIT=1 COCKPIT_NOTIFY=0 CONCLAVE_FAKE_STATE="$T/state"
if [ "$LIVE" = 0 ]; then export PATH="$ROOT/scripts/fake-vendors:$PATH"; fi
GIT=(git -c user.email=e2e@example.com -c user.name=e2e -c init.defaultBranch=main -c commit.gpgsign=false)

pass=0; fail=0
step() {  # step "label" <command…>: run with output in $LOG; pass on exit 0
  local label="$1"; shift
  if "$@" >"$LOG" 2>&1; then pass=$((pass + 1)); printf 'ok   %s\n' "$label"
  else fail=$((fail + 1)); printf 'FAIL %s\n' "$label"; sed 's/^/     /' "$LOG" | tail -15; fi
}
expect_exit() {  # expect_exit CODE command…: pass when the command exits with CODE
  local want="$1"; shift
  "$@"; local rc=$?
  [ "$rc" = "$want" ] || { echo "exit $rc, expected $want"; return 1; }
}
has() { grep -q -- "$1" "$2" || { echo "missing '$1' in $2"; sed -n '1,20p' "$2"; return 1; }; }

# Copy tracked and untracked-not-ignored files only, so local governance.json, markers.txt and jobs stay out.
copy_checkout() {
  if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    (cd "$ROOT" && git ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' f; do
      [ -e "$f" ] && printf '%s\0' "$f"; done | tar --null -T - -cf -) | tar -C "$SYS" -xf -
  else
    cp -R "$ROOT/." "$SYS/"
  fi
}

job_dir() { ls -d "$HUB/$1/.ai/jobs/"*-"$2" 2>/dev/null | tail -1; }

echo "conclave e2e — $([ "$LIVE" = 1 ] && echo live vendors || echo fake vendors)"
step "copy checkout into a temp hub"            copy_checkout
step "install.sh --init"                         env PREFIX="$T/prefix" "$SYS/install.sh" --init
step "governance.json written"                   test -f "$SYS/shared/governance.json"
step "drift check reports 0 drifted"             sh -c "make -s -C '$SYS' drift-check | grep -q ' 0 drifted'"
step "domain instruction files generated"        test -f "$HUB/work/CLAUDE.md" -a -f "$HUB/work/.claude/settings.json" -a -f "$HUB/CROSS-DOMAIN.md"
step "ai roles lists scout"                      sh -c "'$AI' roles | grep -q '^scout'"

cd "$HUB/work" || exit 1
step "dry run prints the orchestration header"   sh -c "'$AI' write 'draft a note' --dry-run | head -1 | grep -q '^Orchestration: write '"
step "data class refuses a prompt-only vendor"   sh -c "'$AI' scout x --vendor grok --dry-run 2>&1 | grep -q 'blocked'; test \"\$(\"$AI\" scout x --vendor grok --dry-run >/dev/null 2>&1; echo \$?)\" = 2"
step "council dry run"                           "$AI" council "A or B?" --dry-run
step "consensus dry run"                         "$AI" consensus "A or B?" --dry-run

step "scout job exits 0 with Acceptance: PASS"   sh -c "'$AI' scout 'List the files here, one line each' > '$T/scout.out' 2>&1 && tail -1 '$T/scout.out' | grep -q '^Acceptance: PASS'"
SJ="$(job_dir work scout)"
step "scout job record is complete"              sh -c "cd '$SJ' && test -f contract.json -a -f events.jsonl -a -f verdict.json -a -f result.md -a -f attempts/1/request.json && grep -q '\"acceptance_status\": \"pass\"' acceptance.json"
step "ai accept re-verifies the scout job"       "$AI" accept "$SJ"

if [ "$LIVE" = 0 ]; then
  step "write job: rejected draft, repair, PASS" sh -c "CONCLAVE_FAKE_FAIL_FIRST_REVIEW=1 '$AI' write 'Write two sentences about the hub. Done means: two sentences.' > '$T/write.out' 2>&1 && tail -1 '$T/write.out' | grep -q '^Acceptance: PASS'"
  WJ="$(job_dir work write)"
  step "each call has its own attempt directory" sh -c "cd '$WJ/attempts' && test -d 1 -a -d 2 && ls -d 1-review-* 2-review-* >/dev/null"
  step "reviewer came from another vendor"       has '"vendor": "codex"' "$WJ/verdict.json"
  step "events record the repair"                has '"purpose": "repair"' "$WJ/events.jsonl"
  step "the accepted artifact is the repair"     has '(repaired)' "$WJ/result.md"
  step "ai jobs shows both jobs as pass"         sh -c "test \"\$('$AI' jobs | grep -c '^pass')\" -ge 2"
fi

cd "$SYS" || exit 1
step "cockpit renders STATUS.md"                 sh -c "bash ops/cockpit.sh && grep -q 'Router health' '$HUB/STATUS.md'"
step "session handoff written"                   sh -c "bash ops/session-handoff.sh --task e2e && ls handoffs/*-handoff.md"
step "vendor handoff refuses a gated model"      sh -c "! bash ops/handoff-to-vendor.sh codex 'continue' > '$T/hv.out' 2>&1 && grep -q 'requires explicit approval' '$T/hv.out'"
step "vendor handoff with approval prints codex" sh -c "bash ops/handoff-to-vendor.sh --approve-top-model codex 'continue' | grep -q 'codex exec'"
step "registry probe emits JSON"                 sh -c "python3 registry/generate.py --probe | python3 -c 'import json,sys; json.load(sys.stdin)'"

cp gate/markers.example.txt gate/markers.txt
REPO="$HUB/public/demo"
mkdir -p "$REPO" && "${GIT[@]}" init -q "$REPO" && echo "hello" > "$REPO/README.md"
step "gate: clean tree"                          gate/publish-gate.sh "$REPO"
step "install pre-commit and pre-push hooks"     gate/install-hooks.sh "$REPO"
step "hook: clean commit passes"                 sh -c "cd '$REPO' && git add -A && $(printf '%q ' "${GIT[@]}")commit -qm init"
KEY="AKIA""ABCDEFGHIJKLMNOP"   # split so this script does not trip its own markers
step "hook: commit with a planted key blocked"   expect_exit 1 sh -c "cd '$REPO' && echo 'key $KEY' > leak.txt && git add leak.txt && $(printf '%q ' "${GIT[@]}")commit -qm leak"

step "docs: relative links and anchors resolve"  python3 "$SYS/scripts/check-links.py" "$SYS"

echo
echo "e2e: $pass passed, $fail failed"
exit "$fail"
