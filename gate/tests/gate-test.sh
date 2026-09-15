#!/usr/bin/env bash
# Regression fixtures for publish-gate.sh. Exit 0 only if every case behaves.
# Run from anywhere: bash gate/tests/gate-test.sh
set -u
GATE="$(cd "$(dirname "$0")/.." && pwd -P)/publish-gate.sh"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
pass=0; fail=0

# Generic markers for the fixtures, handed to the gate through the environment.
# The home-directory marker is assembled from a variable so that this file never trips the
# example marker (/Users/<name>/) when the repository scans itself.
U="/Users"
{
  echo "# fixture markers"
  echo "SECRET_MARKER"
  echo "$U/example/"
  echo 'user@example\.com'
  echo '(800|888)[- .][0-9]{3}[- .][0-9]{4}'
  echo ""
  echo "acme-private"
} > "$T/markers.txt"
export PUBLISH_GATE_MARKERS="$T/markers.txt"

# A copy of the gate in a directory without markers.txt, for the resolution-order fixtures.
mkdir -p "$T/bin"; cp "$GATE" "$T/bin/publish-gate.sh"; chmod +x "$T/bin/publish-gate.sh"
BARE_GATE="$T/bin/publish-gate.sh"

expect() { # expect <blocked|clean> <label> -- cmd...
  local want="$1" label="$2"; shift 3
  local out; out=$("$@" 2>&1); local rc=$?
  local got; if [[ $rc -eq 0 ]]; then got=clean; else got=blocked; fi
  if [[ "$got" == "$want" ]]; then pass=$((pass+1)); printf "ok   %-58s %s\n" "$label" "$got"
  else fail=$((fail+1)); printf "FAIL %-58s want %s got %s\n%s\n" "$label" "$want" "$got" "$out"; fi
}
expect_msg() { # expect_msg <substring> <label> -- cmd...   blocked AND the output contains <substring>
  local want="$1" label="$2"; shift 3
  local out; out=$("$@" 2>&1); local rc=$?
  if [[ $rc -ne 0 && "$out" == *"$want"* ]]; then pass=$((pass+1)); printf "ok   %-58s blocked, says '%s'\n" "$label" "$want"
  else fail=$((fail+1)); printf "FAIL %-58s want blocked with '%s' got rc=%s\n%s\n" "$label" "$want" "$rc" "$out"; fi
}

# non-git tree
mkdir -p "$T/plain/sub"; echo "hello world" > "$T/plain/clean.txt"
expect clean   "non-git clean tree"                  -- "$GATE" "$T/plain"
echo "see $U/example/Documents/notes.csv" > "$T/plain/sub/leak.md"
expect blocked "non-git marker in nested file"       -- "$GATE" "$T/plain"
rm "$T/plain/sub/leak.md"; echo "mail user@example.com" > "$T/plain/.secret"
expect blocked "non-git marker in dotfile"           -- "$GATE" "$T/plain"
rm "$T/plain/.secret"
printf 'PDF\x00\x01 acme-private cookie\x00' > "$T/plain/blob.bin"
expect blocked "non-git marker inside binary"        -- "$GATE" "$T/plain"
rm "$T/plain/blob.bin"
echo "phone 800-555-0100" > "$T/plain/allowed.txt"
expect blocked "non-git phone pattern"               -- "$GATE" "$T/plain"
echo "allowed.txt:1:phone 800-555-0100" > "$T/plain/.publish-gate-allow"
expect clean   "allowlist exact line"                -- "$GATE" "$T/plain"
rm "$T/plain/.publish-gate-allow" "$T/plain/allowed.txt"
expect blocked "nonexistent path"                    -- "$GATE" "$T/nope"

# git repo
git init -q "$T/repo" && git -C "$T/repo" config user.email t@t && git -C "$T/repo" config user.name t
echo "public" > "$T/repo/README.md"; git -C "$T/repo" add -A; git -C "$T/repo" commit -qm init
expect clean   "git clean tree"                      -- "$GATE" "$T/repo"
echo "SECRET_MARKER" > "$T/repo/untracked.txt"
expect blocked "git untracked file with marker"      -- "$GATE" "$T/repo"
echo "untracked.txt" > "$T/repo/.gitignore"
expect clean   "git ignored file skipped"            -- "$GATE" "$T/repo"
rm "$T/repo/untracked.txt" "$T/repo/.gitignore"
echo "ok" > "$T/repo/a.txt"; git -C "$T/repo" add a.txt
expect clean   "staged clean"                        -- "$GATE" --staged "$T/repo"
echo "$U/example/Desktop/x" > "$T/repo/b.txt"; git -C "$T/repo" add b.txt
expect blocked "staged marker"                       -- "$GATE" --staged "$T/repo"
git -C "$T/repo" reset -q; rm "$T/repo/a.txt" "$T/repo/b.txt"
expect blocked "diff mode without upstream"          -- "$GATE" --diff "$T/repo"
git -C "$T/repo" commit -q --allow-empty -m base; base=$(git -C "$T/repo" rev-parse HEAD)
echo "user@example.com" > "$T/repo/c.txt"; git -C "$T/repo" add c.txt; git -C "$T/repo" commit -qm c
expect blocked "diff explicit range marker"          -- "$GATE" --diff "$T/repo" "$base..HEAD"
git -C "$T/repo" rm -q c.txt; git -C "$T/repo" commit -qm rm
expect blocked "diff range: removed marker still in range additions" -- "$GATE" --diff "$T/repo" "$base..HEAD"
base2=$(git -C "$T/repo" rev-parse HEAD); echo "fine" > "$T/repo/d.txt"; git -C "$T/repo" add d.txt; git -C "$T/repo" commit -qm d
expect clean   "diff explicit range clean"           -- "$GATE" --diff "$T/repo" "$base2..HEAD"

# scanner error (unreadable file) must block, not pass
mkdir -p "$T/err"; echo "fine" > "$T/err/ok.txt"; echo "x" > "$T/err/locked.txt"; chmod 000 "$T/err/locked.txt"
if [[ -r "$T/err/locked.txt" ]]; then
  echo "skip scanner error (unreadable file) blocks: this user can read mode-000 files (root?)"
else
  expect blocked "scanner error (unreadable file) blocks"    -- "$GATE" "$T/err"
fi
chmod 644 "$T/err/locked.txt"

# markers resolution: (a) no markers file anywhere, or zero patterns, blocks (fail closed)
mkdir -p "$T/nomark"; echo "nothing to see" > "$T/nomark/x.txt"
expect_msg "no markers file" "no markers file blocks"      -- env -u PUBLISH_GATE_MARKERS "$BARE_GATE" "$T/nomark"
printf '# comments only\n\n' > "$T/empty-markers.txt"
expect_msg "zero patterns"   "markers file with zero patterns blocks" -- env PUBLISH_GATE_MARKERS="$T/empty-markers.txt" "$BARE_GATE" "$T/nomark"

# (b) --markers FILE wins over the environment: only the flag file matches clean.txt ("hello world")
echo "hello" > "$T/flag-markers.txt"
expect blocked "--markers FILE flag used (overrides env)"  -- "$GATE" --markers "$T/flag-markers.txt" "$T/plain"

# (c) <target>/.publish-gate-markers is picked up, and is not a finding itself
mkdir -p "$T/self"; echo "ZEBRA_TOKEN" > "$T/self/.publish-gate-markers"; echo "nothing here" > "$T/self/readme.txt"
expect clean   "target .publish-gate-markers found, not self-flagged" -- env -u PUBLISH_GATE_MARKERS "$BARE_GATE" "$T/self"
echo "token ZEBRA_TOKEN here" > "$T/self/leak.txt"
expect blocked "target .publish-gate-markers pattern blocks" -- env -u PUBLISH_GATE_MARKERS "$BARE_GATE" "$T/self"

# Regression: scan the index and history, even after the working copy changes.
printf 'BLOB\x00SECRET_MARKER\x00' > "$T/repo/staged.bin"
git -C "$T/repo" add staged.bin
printf 'BLOB\x00clean\x00' > "$T/repo/staged.bin"
expect blocked "staged binary differs from working tree" -- "$GATE" --staged "$T/repo"
rm "$T/repo/staged.bin"
expect blocked "staged binary absent from working tree" -- "$GATE" --staged "$T/repo"
history_base=$(git -C "$T/repo" rev-parse HEAD)
git -C "$T/repo" commit -qm binary
git -C "$T/repo" add -u
git -C "$T/repo" commit -qm remove-binary
expect blocked "deleted binary marker in pushed history" -- "$GATE" --diff "$T/repo" "$history_base..HEAD"

# A marker beyond the previous 5 MB cutoff still blocks.
dd if=/dev/zero of="$T/plain/large.bin" bs=1048576 count=6 2>/dev/null
printf 'SECRET_MARKER' >> "$T/plain/large.bin"
expect blocked "binary larger than 5 MB" -- "$GATE" "$T/plain"
rm "$T/plain/large.bin"

# Filenames and exact-line allowlists apply to all modes.
echo SECRET_MARKER > "$T/repo/file with spaces.txt"
git -C "$T/repo" add 'file with spaces.txt'
expect blocked "staged filename with spaces" -- "$GATE" --staged "$T/repo"
echo 'file with spaces.txt:1:SECRET_MARKER' > "$T/repo/.publish-gate-allow"
expect clean "staged exact-line exception" -- "$GATE" --staged "$T/repo"

echo '[' > "$T/invalid-markers.txt"
expect_msg "invalid pattern" "invalid regex blocks" -- "$GATE" --markers "$T/invalid-markers.txt" "$T/plain"
expect blocked "invalid revision range blocks" -- "$GATE" --diff "$T/repo" DOES_NOT_EXIST

# Merge-only content must be scanned even when neither parent contains it.
git init -q "$T/merge"
git -C "$T/merge" config user.email t@t
git -C "$T/merge" config user.name t
echo base > "$T/merge/base.txt"
git -C "$T/merge" add .
git -C "$T/merge" commit -qm base
git -C "$T/merge" checkout -qb side
echo side > "$T/merge/side.txt"
git -C "$T/merge" add .
git -C "$T/merge" commit -qm side
git -C "$T/merge" checkout -qb target HEAD~1 || exit 1
echo main > "$T/merge/main.txt"
git -C "$T/merge" add .
git -C "$T/merge" commit -qm main
merge_base=$(git -C "$T/merge" rev-parse HEAD)
git -C "$T/merge" merge --no-commit --no-ff side >/dev/null 2>&1 || exit 1
printf 'BLOB\x00SECRET_MARKER\x00' > "$T/merge/merged.bin"
git -C "$T/merge" add .
git -C "$T/merge" commit -qm merge || exit 1
[[ $(git -C "$T/merge" rev-list --parents -n 1 HEAD | wc -w) -eq 3 ]] || exit 1
expect blocked "marker introduced by merge commit" -- "$GATE" --diff "$T/merge" "$merge_base..HEAD"

# A scanner can fail without stderr; its exit status must still block.
mkdir -p "$T/failing-bin"
printf '#!/bin/sh\nexit 2\n' > "$T/failing-bin/grep"
chmod +x "$T/failing-bin/grep"
expect blocked "silent grep error blocks" -- env PATH="$T/failing-bin:$PATH" "$GATE" "$T/plain"

echo "gate tests: $pass passed, $fail failed"
[[ $fail -eq 0 ]]
