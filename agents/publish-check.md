---
name: publish-check
description: Private-marker and secret scanner for arbitrary files, diffs, or directories — wraps the publish gate
---

# Publish Check Agent

Scan any file, diff, or directory for private markers before sharing or publishing.

## What it does

Wraps `_system/gate/publish-gate.sh` for flexible input:
- `--file FILE` — scan a single file
- `--diff` — scan the current staged git diff
- `--stdin` — pipe content for scanning
- `DIR` — scan a directory tree (same as the gate directly)

What counts as a marker is the markers file (`_system/gate/markers.txt`, or `.publish-gate-markers` in the scanned repo): home-directory paths, private folder names, personal email addresses, secret prefixes, whatever the operator has listed.

## Usage

Ask: "check this file for private markers" or "scan my diff before pushing"

The agent runs: `_system/gate/publish-check.sh`

## Key paths

- Wrapper: `_system/gate/publish-check.sh`
- Gate engine: `_system/gate/publish-gate.sh`
- Markers: `_system/gate/markers.txt` · Allowlist: `.publish-gate-allow` in the scanned directory

## When to use

- Before pushing any code to a public repo
- Before sharing files outside the workstation
- Before any pipeline that moves content from a private domain to a public one
- Any time you're unsure if content contains private markers

The gate is fail-closed: a scan error blocks, and so does a missing markers file. Report a block; never work around it.
