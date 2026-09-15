---
name: registry-audit
description: Refresh the system registry and flag issues — failed vendor probes, unloaded scheduled jobs, missing keys
---

# Registry Audit Agent

Refresh the capability registry and audit it for problems.

## What it does

1. Snapshots the current `registry.json` (keeps the last 10 snapshots)
2. Re-probes every vendor CLI, MCP server list, skill, scheduled job, and model in `policy.json`
3. Diffs against the previous snapshot and prints what changed
4. Flags issues; the exit code is the issue count (0 = clean)

## Usage

Ask: "audit the registry" or "check infrastructure status"

The agent runs: `_system/ops/registry-audit.sh`

## Key paths

- Registry: `_system/registry/registry.json` (source) · `_system/registry/REGISTRY.md` (view)
- Snapshots: `_system/registry/snapshots/`
- Generator: `_system/registry/generate.py` · Config: `_system/registry/config.json`

## What it flags

- Vendor probes that failed or timed out (CLI missing, not logged in, key unset)
- Scheduled jobs that are not loaded or exited non-zero
- Models in `policy.json` marked unavailable
- Anything a probe recorded as an error — failures are listed, never omitted
