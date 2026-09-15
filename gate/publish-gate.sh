#!/usr/bin/env bash
# conclave publish gate: a fail-closed scanner for private markers, run before anything goes public.
#
# USAGE
#   publish-gate.sh [--markers FILE] <path>                 tree mode
#   publish-gate.sh [--markers FILE] --staged <repo>        staged additions (pre-commit hook)
#   publish-gate.sh [--markers FILE] --diff <repo> [A..B]   commits about to be pushed (pre-push hook)
#
#   tree     scans every file: in a git repo, tracked + untracked-not-ignored (dotfiles included);
#            outside git, everything `find` reaches except .git/ directories.
#   staged   scans every added line in the index, plus every binary added or modified in the index.
#   diff     scans every added line of every commit in the range (each commit becomes public
#            history, so the net diff is not enough), plus binaries touched by those commits.
#            Default range: @{push}..HEAD, then @{upstream}..HEAD; BLOCKS if neither exists.
#
# MARKERS FILE
#   Patterns are never hardcoded here. They come from a markers file: one POSIX extended regular
#   expression per line (grep -E syntax), matched case-insensitively. Blank lines and lines whose
#   first non-blank character is # are ignored; leading/trailing whitespace and a trailing CR are
#   stripped from each pattern. Resolution order, first match wins:
#     1. --markers FILE                    (command line)
#     2. $PUBLISH_GATE_MARKERS             (environment)
#     3. <target>/.publish-gate-markers    (inside the scanned path)
#     4. <script dir>/markers.txt          (copy markers.example.txt to markers.txt and edit it;
#                                           markers.txt is gitignored because it names your secrets)
#   A file named by 1 or 2 must exist. If no file is found, or the file yields zero patterns,
#   or a pattern is not a valid regex, the gate BLOCKS. It never scans with an empty set.
#
# ALLOWLIST
#   <target>/.publish-gate-allow: one exact finding line per allowed hit, verbatim as this gate
#   prints it (tree mode "path:line:text", staged/diff modes the diff line including its leading
#   "+", binaries "path:binary: ..."). Blank lines and # comments are ignored. The allowlist and
#   the .publish-gate-markers file inside the target are never findings themselves; commit them
#   only if their contents are acceptable in public.
#
# BINARIES
#   grep skips binary files; every binary up to 5 MB is also searched with `strings`, or with
#   `grep -a -o -E` when `strings` is not installed.
#
# EXIT CODES
#   0  clean
#   1  BLOCKED: a marker was found, no usable markers file, a scan or git error occurred, the
#      range could not be resolved, or the path does not exist. Every error blocks; the gate
#      never fails open.
#
# Requires bash 3.2+, git, grep, sed, find, xargs, stat, mktemp. Runs on Linux and macOS.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
USAGE="usage: publish-gate.sh [--markers FILE] [--staged|--diff] <path> [range]"

MODE="tree"
MARKERS_OPT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged)    MODE="staged"; shift ;;
    --diff)      MODE="diff"; shift ;;
    --markers)   [[ $# -ge 2 ]] || { echo "PUBLISH GATE: BLOCKED — --markers needs a FILE"; exit 1; }
                 MARKERS_OPT="$2"; shift 2 ;;
    --markers=*) MARKERS_OPT="${1#--markers=}"; shift ;;
    -h|--help)   echo "$USAGE"; exit 0 ;;
    --)          shift; break ;;
    -*)          echo "PUBLISH GATE: BLOCKED — unknown option: $1"; echo "$USAGE"; exit 1 ;;
    *)           break ;;
  esac
done
[[ $# -ge 1 ]] || { echo "PUBLISH GATE: BLOCKED — missing path"; echo "$USAGE"; exit 1; }
RAW_TARGET="$1"
RANGE="${2:-}"
TARGET="$(cd "$RAW_TARGET" 2>/dev/null && pwd -P)" || { echo "PUBLISH GATE: BLOCKED — path does not exist: $RAW_TARGET"; exit 1; }

TMP=$(mktemp -d 2>/dev/null) || { echo "PUBLISH GATE: BLOCKED — cannot create temp dir"; exit 1; }
trap 'rm -rf "$TMP"' EXIT
FOUND="$TMP/found"; ERR="$TMP/err"; : > "$FOUND"; : > "$ERR"

# ---- markers -----------------------------------------------------------------------------------
MARKERS=()
MARKERS_FILE=""
resolve_markers_file() {
  local c
  if [[ -n "$MARKERS_OPT" ]]; then
    [[ -f "$MARKERS_OPT" ]] || { echo "PUBLISH GATE: BLOCKED — no markers file (--markers $MARKERS_OPT does not exist)"; exit 1; }
    MARKERS_FILE="$MARKERS_OPT"; return 0
  fi
  if [[ -n "${PUBLISH_GATE_MARKERS:-}" ]]; then
    [[ -f "$PUBLISH_GATE_MARKERS" ]] || { echo "PUBLISH GATE: BLOCKED — no markers file (PUBLISH_GATE_MARKERS=$PUBLISH_GATE_MARKERS does not exist)"; exit 1; }
    MARKERS_FILE="$PUBLISH_GATE_MARKERS"; return 0
  fi
  for c in "$TARGET/.publish-gate-markers" "$SCRIPT_DIR/markers.txt"; do
    if [[ -f "$c" ]]; then MARKERS_FILE="$c"; return 0; fi
  done
  echo "PUBLISH GATE: BLOCKED — no markers file (searched: --markers FILE, \$PUBLISH_GATE_MARKERS, $TARGET/.publish-gate-markers, $SCRIPT_DIR/markers.txt)"
  exit 1
}
load_markers() {  # one pattern per line; blank lines and # comments ignored; whitespace and CR trimmed
  local f="$1" line
  [[ -r "$f" ]] || { echo "PUBLISH GATE: BLOCKED — markers file not readable: $f"; exit 1; }
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    MARKERS+=("$line")
  done < "$f"
}
resolve_markers_file
load_markers "$MARKERS_FILE"
if [[ ${#MARKERS[@]} -eq 0 ]]; then
  echo "PUBLISH GATE: BLOCKED — no markers file with patterns ($MARKERS_FILE yields zero patterns)"
  exit 1
fi
COMBINED=$(IFS='|'; printf '%s' "${MARKERS[*]}")
grep -iE -e "$COMBINED" /dev/null 2>"$TMP/re_err"; re_rc=$?   # 1 = valid regex, no match; 2 = invalid regex
if [[ $re_rc -eq 2 ]]; then
  echo "PUBLISH GATE: BLOCKED — invalid pattern in $MARKERS_FILE:"
  sed 's/^/  /' "$TMP/re_err"
  exit 1
fi

# ---- allowlist ---------------------------------------------------------------------------------
ALLOW="$TARGET/.publish-gate-allow"
ALLOWED="$TMP/allow"; : > "$ALLOWED"
if [[ -f "$ALLOW" ]]; then
  grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$ALLOW" > "$ALLOWED" 2>>"$ERR"
fi

# ---- portability helpers -----------------------------------------------------------------------
file_size() {  # bytes; prints 0 when unknown, so an unknown size is still scanned (fail closed)
  local s
  s=$(stat -f %z "$1" 2>/dev/null) && [[ "$s" =~ ^[0-9]+$ ]] && { echo "$s"; return 0; }
  s=$(stat -c %s "$1" 2>/dev/null) && [[ "$s" =~ ^[0-9]+$ ]] && { echo "$s"; return 0; }
  echo 0
}
if command -v strings >/dev/null 2>&1; then
  extract_strings() { strings "$1"; }
else
  extract_strings() { LC_ALL=C grep -a -i -o -E -e "$COMBINED" "$1"; }
fi

# ---- filters -----------------------------------------------------------------------------------
# The allowlist and markers files inside the target are never findings. Everything else that
# reaches here already matched a marker.
policy_filter() { sed -E 's|^\./||' | grep -vE '^\.publish-gate-(allow|markers):' || true; }
allow_filter() { policy_filter | { if [[ -s "$ALLOWED" ]]; then grep -vFxf "$ALLOWED" || true; else cat; fi; }; }

# ---- scanners ----------------------------------------------------------------------------------
# grep exits 0 match, 1 no match, 2 error. xargs folds both 1 and 2 into its own status on BSD, so
# errors are detected through stderr (captured into $ERR); any stderr output blocks.
scan_files_z() {  # reads NUL-separated paths on stdin, relative to $TARGET; prints path:line:text
  ( cd "$TARGET" && xargs -0 -r grep -IiEnH -e "$COMBINED" -- ) 2>>"$ERR"
  local rc=$?
  case $rc in
    0|1|123) ;;
    *) echo "grep via xargs exited $rc" >> "$ERR" ;;
  esac
  return 0
}
scan_binaries_z() {  # reads NUL-separated paths on stdin; strings-scans binaries up to 5 MB
  local f hit
  while IFS= read -r -d '' f; do
    [[ -f "$TARGET/$f" ]] || continue
    grep -Iq . "$TARGET/$f" 2>/dev/null && continue        # text file: grep already covered it
    [[ $(file_size "$TARGET/$f") -le 5242880 ]] || continue
    hit=$(extract_strings "$TARGET/$f" 2>>"$ERR" | grep -ioE -e "$COMBINED" | head -n 1)
    [[ -n "$hit" ]] && echo "${f#./}:binary: private marker inside binary ($hit)"
  done
  return 0
}

# ---- modes -------------------------------------------------------------------------------------
case "$MODE" in
  tree)
    if git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
      git -C "$TARGET" ls-files -z --cached --others --exclude-standard 2>>"$ERR" > "$TMP/list" || echo "git ls-files failed" >> "$ERR"
    else
      ( cd "$TARGET" && find . -type f ! -path '*/.git/*' -print0 ) > "$TMP/list" 2>>"$ERR"
    fi
    scan_files_z    < "$TMP/list" | allow_filter >> "$FOUND"
    scan_binaries_z < "$TMP/list" | allow_filter >> "$FOUND"
    ;;
  staged)
    git -C "$TARGET" diff --cached --unified=0 --no-color 2>>"$ERR" > "$TMP/diff" || echo "git diff --cached failed" >> "$ERR"
    grep -E '^\+' "$TMP/diff" | grep -vE '^\+\+\+' | grep -iE -e "$COMBINED" 2>>"$ERR" | allow_filter >> "$FOUND"
    # binaries added to or modified in the index
    git -C "$TARGET" diff --cached --name-only -z --diff-filter=AM 2>>"$ERR" | scan_binaries_z | allow_filter >> "$FOUND"
    ;;
  diff)
    if [[ -z "$RANGE" ]]; then
      if git -C "$TARGET" rev-parse --verify -q '@{push}' >/dev/null 2>&1; then RANGE='@{push}..HEAD'
      elif git -C "$TARGET" rev-parse --verify -q '@{upstream}' >/dev/null 2>&1; then RANGE='@{upstream}..HEAD'
      else echo "PUBLISH GATE: BLOCKED — no @{push} or @{upstream} for $(basename "$TARGET"); pass an explicit range"; exit 1; fi
    fi
    # every commit in the range becomes public history, so scan each commit's additions, not the net diff
    git -C "$TARGET" log -p --unified=0 --no-color --format='commit %h' "$RANGE" -- 2>>"$ERR" > "$TMP/diff" || echo "git log -p $RANGE failed" >> "$ERR"
    grep -E '^\+' "$TMP/diff" | grep -vE '^\+\+\+' | grep -iE -e "$COMBINED" 2>>"$ERR" | allow_filter >> "$FOUND"
    git -C "$TARGET" log --name-only -z --diff-filter=AM --format= "$RANGE" -- 2>>"$ERR" | tr -s '\0' | scan_binaries_z | allow_filter >> "$FOUND"
    ;;
esac

# ---- verdict -----------------------------------------------------------------------------------
if [[ -s "$ERR" ]]; then
  echo "PUBLISH GATE: BLOCKED — scan error ($MODE mode, $(basename "$TARGET")):"
  head -n 10 "$ERR" | sed 's/^/  /'
  exit 1
fi
if [[ -s "$FOUND" ]]; then
  echo "PUBLISH GATE: BLOCKED — private markers ($MODE mode, $(basename "$TARGET")):"
  head -n 20 "$FOUND" | sed 's/^/  /'
  echo "  Fix the content, or add the exact line to .publish-gate-allow after review."
  exit 1
fi
echo "PUBLISH GATE: clean ($MODE mode, $(basename "$TARGET"))"
exit 0
