#!/usr/bin/env bash
# conclave installer: put `ai` on your PATH, check prerequisites, optionally bootstrap a hub.
#
#   ./install.sh                 symlink router/ai → ~/.local/bin/ai, report what is installed
#   ./install.sh --init          also run `ai init` (governance.json from the example, domain folders, instruction files)
#   ./install.sh --hub DIR       with --init: use DIR as the hub instead of the parent of this checkout
#   ./install.sh --name NAME     link the CLI under another name (default: ai)
#   PREFIX=/usr/local ./install.sh   install the link under $PREFIX/bin instead of ~/.local/bin
#
# Nothing here needs sudo, network, or a vendor account. Re-running is safe.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
BIN="${PREFIX:-$HOME/.local}/bin"
NAME="ai"; INIT=0; HUB=""
while [ $# -gt 0 ]; do
  case "$1" in
    --init) INIT=1 ;;
    --hub) HUB="$2"; shift ;;
    --name) NAME="$2"; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
  shift
done

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

echo "conclave — $HERE"
echo
echo "Prerequisites"
if command -v python3 >/dev/null 2>&1; then
  pv=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then ok "python3 $pv"; else warn "python3 $pv found; 3.9+ required"; fi
else
  warn "python3 not found (required)"; exit 1
fi
command -v git >/dev/null 2>&1 && ok "git" || warn "git not found (the publish gate's --staged/--diff modes need it)"
command -v bash >/dev/null 2>&1 && ok "bash $(bash -c 'echo ${BASH_VERSION%%(*}')" || warn "bash not found"
echo
echo "Vendor clients (configure role defaults for the clients you install)"
for v in claude codex grok; do
  if command -v "$v" >/dev/null 2>&1; then ok "$v  ($(command -v "$v"))"; else warn "$v not on PATH"; fi
done
if python3 -c 'import google.genai' >/dev/null 2>&1; then ok "gemini: google-genai SDK importable"; else warn "gemini: pip install google-genai (and export GEMINI_API_KEY)"; fi
echo
echo "CLI link"
mkdir -p "$BIN"
if ln -sfn "$HERE/router/ai" "$BIN/$NAME"; then ok "$BIN/$NAME → router/ai"; else warn "could not link into $BIN"; fi
case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN is not on your PATH — add: export PATH=\"$BIN:\$PATH\"" ;; esac
echo
if [ "$INIT" = 1 ]; then
  echo "Hub"
  if [ -n "$HUB" ]; then "$HERE/router/ai" init --hub "$HUB"; else "$HERE/router/ai" init; fi
elif [ ! -f "$HERE/shared/governance.json" ]; then
  echo "Next"
  echo "  $NAME init            # bootstrap a hub around this checkout (or: ./install.sh --init [--hub DIR])"
  echo "  $NAME smoke           # ping every vendor at tier 1"
  echo "  make test             # offline tests: router + publish-gate fixtures"
fi
