#!/usr/bin/env bash
# conclave publish gate: convenience wrapper that runs publish-gate.sh over arbitrary input.
#
#   publish-check.sh [--markers FILE] --file FILE   scan a single file
#   publish-check.sh [--markers FILE] --diff        scan the staged git diff (falls back to the unstaged diff)
#   publish-check.sh [--markers FILE] --stdin       scan standard input
#   publish-check.sh [--markers FILE] DIR           scan a directory tree (delegates to publish-gate.sh)
#
# Single files, diffs, and stdin are copied into a temporary directory and scanned in tree mode,
# so no allowlist applies to them and the markers file is resolved from --markers,
# $PUBLISH_GATE_MARKERS, or <script dir>/markers.txt. For hook-grade checks of a repository use
# publish-gate.sh --staged / --diff directly. Exit 0 clean, 1 blocked or error.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd -P)"
GATE="$HERE/publish-gate.sh"

usage() {
  echo "Usage: publish-check.sh [--markers FILE] [--file FILE | --diff | --stdin | DIR]"
  echo "  --markers FILE  Use this markers file instead of the default resolution"
  echo "  --file FILE     Scan a single file"
  echo "  --diff          Scan the staged git diff (falls back to the unstaged diff)"
  echo "  --stdin         Read from stdin"
  echo "  DIR             Scan a directory tree (delegates to publish-gate.sh)"
  exit 1
}

[ -x "$GATE" ] || { echo "publish-check: gate not found or not executable: $GATE"; exit 1; }

MARKERS_ARGS=()
if [ "${1:-}" = "--markers" ]; then
  [ -n "${2:-}" ] || usage
  MARKERS_ARGS=(--markers "$2")
  shift 2
fi
[ $# -eq 0 ] && usage

run_gate() {  # run_gate <path>
  if [ ${#MARKERS_ARGS[@]} -gt 0 ]; then
    "$GATE" "${MARKERS_ARGS[@]}" "$1"
  else
    "$GATE" "$1"
  fi
}

MODE="$1"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

case "$MODE" in
  --file)
    [ -n "${2:-}" ] || usage
    FILE="$2"
    [ -f "$FILE" ] || { echo "File not found: $FILE"; exit 1; }
    mkdir -p "$WORK/scan"
    cp "$FILE" "$WORK/scan/"
    run_gate "$WORK/scan"
    ;;
  --diff)
    git rev-parse --git-dir >/dev/null 2>&1 || { echo "publish-check: not inside a git repository"; exit 1; }
    git diff --cached --no-color > "$WORK/diff.patch"
    LABEL="staged"
    if [ ! -s "$WORK/diff.patch" ]; then
      git diff --no-color > "$WORK/diff.patch"
      LABEL="unstaged"
    fi
    if [ ! -s "$WORK/diff.patch" ]; then
      echo "No diff to scan."
      exit 0
    fi
    echo "publish-check: scanning $LABEL diff"
    mkdir -p "$WORK/scan"
    cp "$WORK/diff.patch" "$WORK/scan/$LABEL.diff"
    run_gate "$WORK/scan"
    ;;
  --stdin)
    mkdir -p "$WORK/scan"
    cat > "$WORK/scan/input.txt"
    run_gate "$WORK/scan"
    ;;
  -*)
    echo "Unknown option: $MODE"
    usage
    ;;
  *)
    if [ -d "$MODE" ]; then
      run_gate "$MODE"
    else
      echo "Not a directory: $MODE"
      usage
    fi
    ;;
esac
