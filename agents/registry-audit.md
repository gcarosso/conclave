---
name: registry-audit
description: Refresh the local capability registry and report changed or failed probes.
---

# Registry audit

Run `_system/ops/registry-audit.sh` when asked to audit the registry or check infrastructure status. It snapshots the existing registry, runs the configured probes, compares results, and reports issues.

Read `_system/registry/registry.json` and its `REGISTRY.md` view. Configuration is in `registry/config.json`; previous observations are in `registry/snapshots/`.

Report failed probes, missing scheduled jobs, nonzero job exits, and configured unavailable models with their observation dates. Distinguish version/configuration checks from live authentication and model calls. Do not claim a model was tested because it appears in the policy catalog. Keep local paths and configuration details in the private workspace.
