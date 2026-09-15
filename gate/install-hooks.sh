#!/usr/bin/env bash
# conclave publish gate: install pre-commit and pre-push hooks into one or more repositories.
#
#   install-hooks.sh [--force] <repo> [<repo>...]
#
# pre-commit runs  publish-gate.sh --staged <repo>   (every added line and binary in the index)
# pre-push   runs  publish-gate.sh --diff <repo> ... (every commit about to be pushed, per ref)
#
# Hooks call the gate by the absolute path of this checkout, resolved now; move the checkout and
# the hooks fail closed until you re-run this installer. An existing hook that is not ours
# (identified by the line "# conclave publish-gate hook") is left alone unless --force is given.
# Exit 0 when every requested hook is installed, 1 otherwise.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd -P)"
GATE="$HERE/publish-gate.sh"
MARK="# conclave publish-gate hook"
FORCE=0

usage() { echo "usage: install-hooks.sh [--force] <repo> [<repo>...]"; exit 1; }

REPOS=()
for arg in "$@"; do
  case "$arg" in
    --force)   FORCE=1 ;;
    -h|--help) usage ;;
    -*)        echo "install-hooks: unknown option: $arg"; usage ;;
    *)         REPOS+=("$arg") ;;
  esac
done
[[ ${#REPOS[@]} -gt 0 ]] || usage
[[ -x "$GATE" ]] || { echo "install-hooks: gate not found or not executable: $GATE"; exit 1; }

write_hook() {  # write_hook <hooks dir> <name> <body>
  local dir="$1" name="$2" body="$3" path="$1/$2"
  if [[ -e "$path" ]] && ! grep -qF "$MARK" "$path" && [[ $FORCE -eq 0 ]]; then
    echo "  refused  $path (existing hook is not ours; use --force to overwrite)"
    return 1
  fi
  printf '%s\n' "$body" > "$path" || { echo "  failed   $path (cannot write)"; return 1; }
  chmod +x "$path" || { echo "  failed   $path (cannot chmod)"; return 1; }
  echo "  installed $path"
  return 0
}

# Both hooks resolve the repository from git itself so they work from worktrees and subdirectories.
PRE_COMMIT="#!/usr/bin/env bash
$MARK
# Installed by install-hooks.sh. Scans staged additions; a non-zero exit aborts the commit.
GATE='$GATE'
REPO=\"\$(git rev-parse --show-toplevel)\" || exit 1
[ -x \"\$GATE\" ] || { echo \"publish-gate hook: gate not found at \$GATE (re-run install-hooks.sh)\"; exit 1; }
exec \"\$GATE\" --staged \"\$REPO\""

PRE_PUSH="#!/usr/bin/env bash
$MARK
# Installed by install-hooks.sh. Scans every commit about to be pushed; a non-zero exit aborts the push.
# git passes the remote name as \$1 and one line per ref on stdin: <local ref> <local sha> <remote ref> <remote sha>.
GATE='$GATE'
REPO=\"\$(git rev-parse --show-toplevel)\" || exit 1
[ -x \"\$GATE\" ] || { echo \"publish-gate hook: gate not found at \$GATE (re-run install-hooks.sh)\"; exit 1; }
remote=\"\${1:-origin}\"
zero='0000000000000000000000000000000000000000'
status=0; scanned=0
while read -r local_ref local_sha remote_ref remote_sha; do
  [ \"\$local_sha\" = \"\$zero\" ] && continue                    # deleting a remote ref: nothing to publish
  scanned=1
  if [ \"\$remote_sha\" = \"\$zero\" ]; then
    # New remote ref: scan back to the newest commit this remote already has; with no remote-tracking
    # refs at all (empty remote) scan the whole history. Word splitting of rev-parse output is intended.
    # shellcheck disable=SC2046
    base=\$(git merge-base \"\$local_sha\" \$(git rev-parse --remotes=\"\$remote\") 2>/dev/null)
    if [ -n \"\$base\" ]; then range=\"\$base..\$local_sha\"; else range=\"\$local_sha\"; fi
  else
    range=\"\$remote_sha..\$local_sha\"
  fi
  \"\$GATE\" --diff \"\$REPO\" \"\$range\" </dev/null || status=1
done
if [ \"\$scanned\" -eq 0 ]; then \"\$GATE\" --diff \"\$REPO\" </dev/null || status=1; fi
exit \$status"

rc=0
for repo in "${REPOS[@]}"; do
  if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
    echo "$repo: not a git repository"; rc=1; continue
  fi
  hooks="$(git -C "$repo" rev-parse --git-path hooks)"
  case "$hooks" in
    /*) ;;
    *) hooks="$(cd "$repo" && pwd -P)/$hooks" ;;
  esac
  mkdir -p "$hooks" || { echo "$repo: cannot create $hooks"; rc=1; continue; }
  echo "$repo:"
  write_hook "$hooks" pre-commit "$PRE_COMMIT" || rc=1
  write_hook "$hooks" pre-push   "$PRE_PUSH"   || rc=1
done
echo "gate: $GATE"
exit $rc
