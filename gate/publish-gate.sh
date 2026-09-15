#!/usr/bin/env bash
# conclave publish gate: a fail-closed scanner for private markers, run before anything goes public.
#
# USAGE
#   publish-gate.sh [--markers FILE] <path>                 tree mode
#   publish-gate.sh [--markers FILE] --staged <repo>        staged file versions (pre-commit hook)
#   publish-gate.sh [--markers FILE] --diff <repo> [A..B]   commits about to be pushed (pre-push hook)
#
#   tree     scans every file: in a git repo, tracked + untracked-not-ignored (dotfiles included);
#            outside git, everything `find` reaches except .git/ directories.
#   staged   scans the complete index blob of each added or modified file.
#   diff     scans changed file blobs in every commit in the range, including merge commits.
#            Reads Git objects, independent of the working tree. Default range: @{push}..HEAD,
#            then @{upstream}..HEAD; blocks if neither exists.
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
#   prints it: "path:line:text" or "path:binary: private marker inside binary (match)".
#   Blank lines and # comments are ignored. The allowlist and .publish-gate-markers files
#   are excluded from findings. Review their contents separately before committing them.
#   Existing diff-line exceptions beginning with "+" must be regenerated for blob scanning.
#
# BINARIES
#   All file sizes are scanned as raw bytes using grep -a. Compressed, encoded, or encrypted
#   contents are not decoded. A clean scan means no configured pattern matched in this scope.
#
# EXIT CODES
#   0  clean
#   1  BLOCKED: a marker was found, no usable markers file, a scan or git error occurred, the
#      range could not be resolved, or the path does not exist. Every error blocks; the gate
#      never fails open.
#
# Requires bash 3.2+, git, grep, sed, find, mktemp. Runs on Linux and macOS.
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
if [[ $re_rc -gt 1 ]]; then
  echo "PUBLISH GATE: BLOCKED — invalid pattern in $MARKERS_FILE:"
  sed 's/^/  /' "$TMP/re_err"
  exit 1
fi

# ---- allowlist ---------------------------------------------------------------------------------
ALLOW="$TARGET/.publish-gate-allow"
ALLOWED="$TMP/allow"; : > "$ALLOWED"
if [[ -f "$ALLOW" ]]; then
  grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$ALLOW" > "$ALLOWED" 2>>"$ERR"; allow_rc=$?
  [[ $allow_rc -le 1 ]] || echo "cannot read allowlist ($allow_rc)" >> "$ERR"
fi

# ---- scanners -------------------------------------------------------------------------------
# Scan raw bytes with grep -a, including binary files of any size. This does not decode
# archives, images, encrypted data, or other encodings. A matching configured regex blocks.
scan_file() {  # scan_file <file> <display path>
  local source="$1" label="$2" rc binary=0 line
  case "$label" in .publish-gate-allow|.publish-gate-markers) return 0 ;; esac
  LC_ALL=C grep -Iq . "$source" 2>>"$ERR"; rc=$?
  if [[ $rc -gt 1 ]]; then echo "file classification failed: $label ($rc)" >> "$ERR"; return; fi
  [[ $rc -eq 1 ]] && binary=1
  if [[ $binary -eq 1 ]]; then
    LC_ALL=C grep -aioE -e "$COMBINED" "$source" > "$TMP/hits" 2>>"$ERR"; rc=$?
    while IFS= read -r line || [[ -n "$line" ]]; do
      printf '%s:binary: private marker inside binary (%s)\n' "$label" "$line" >> "$TMP/raw"
    done < "$TMP/hits"
  else
    LC_ALL=C grep -anE -i -e "$COMBINED" "$source" > "$TMP/hits" 2>>"$ERR"; rc=$?
    while IFS= read -r line || [[ -n "$line" ]]; do
      printf '%s:%s\n' "$label" "$line" >> "$TMP/raw"
    done < "$TMP/hits"
  fi
  [[ $rc -le 1 ]] || echo "grep failed: $label ($rc)" >> "$ERR"
  return 0
}

scan_blob() {  # scan_blob <git revision:path> <display path>
  if git -C "$TARGET" cat-file blob "$1" > "$TMP/blob" 2>>"$ERR"; then
    scan_file "$TMP/blob" "$2"
  else
    echo "cannot read blob $1" >> "$ERR"
  fi
}

: > "$TMP/raw"
case "$MODE" in
  tree)
    if git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
      git -C "$TARGET" ls-files -z --cached --others --exclude-standard > "$TMP/list" 2>>"$ERR" || echo "git ls-files failed" >> "$ERR"
    else
      ( cd "$TARGET" && find . -type f ! -path '*/.git/*' -print0 ) > "$TMP/list" 2>>"$ERR" || echo "find failed" >> "$ERR"
    fi
    while IFS= read -r -d '' f; do scan_file "$TARGET/$f" "${f#./}"; done < "$TMP/list"
    ;;
  staged)
    git -C "$TARGET" ls-files --unmerged > "$TMP/unmerged" 2>>"$ERR" || echo "git ls-files failed" >> "$ERR"
    [[ ! -s "$TMP/unmerged" ]] || echo "index has unmerged entries" >> "$ERR"
    git -C "$TARGET" diff --cached --name-only -z --diff-filter=ACMRT --no-renames > "$TMP/list" 2>>"$ERR" || echo "git diff --cached failed" >> "$ERR"
    while IFS= read -r -d '' f; do scan_blob ":$f" "$f"; done < "$TMP/list"
    ;;
  diff)
    if [[ -z "$RANGE" ]]; then
      if git -C "$TARGET" rev-parse --verify -q '@{push}' >/dev/null 2>&1; then RANGE='@{push}..HEAD'
      elif git -C "$TARGET" rev-parse --verify -q '@{upstream}' >/dev/null 2>&1; then RANGE='@{upstream}..HEAD'
      else echo "PUBLISH GATE: BLOCKED — no upstream; pass an explicit revision range"; exit 1; fi
    fi
    git -C "$TARGET" rev-list "$RANGE" -- > "$TMP/commits" 2>>"$ERR" || echo "git rev-list failed" >> "$ERR"
    while IFS= read -r commit; do
      # -m includes changes relative to each merge parent; --root includes initial commits.
      git -C "$TARGET" diff-tree --root -m --no-commit-id --name-only --diff-filter=ACMRT --no-renames -r -z "$commit" > "$TMP/list" 2>>"$ERR" || echo "git diff-tree failed" >> "$ERR"
      while IFS= read -r -d '' f; do scan_blob "$commit:$f" "$f"; done < "$TMP/list"
    done < "$TMP/commits"
    ;;
esac

# Exact-line exceptions apply consistently to tree, staged blobs, and historical blobs.
if [[ -s "$ALLOWED" ]]; then
  grep -vFxf "$ALLOWED" "$TMP/raw" > "$FOUND" 2>>"$ERR"; filter_rc=$?
  [[ $filter_rc -le 1 ]] || echo "allowlist filter failed ($filter_rc)" >> "$ERR"
else
  cat "$TMP/raw" > "$FOUND" || echo "cannot read findings" >> "$ERR"
fi

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
