# Component reference

| Component | Entry point | Output or responsibility |
|---|---|---|
| CLI | `router/ai` | Commands, flags, domain detection, and terminal output |
| Kernel | `router/kernel.py` | Routing, contracts, locks, dispatch, repair, escalation, and job state |
| Adapters | `router/adapters.py` | Claude, Codex, Grok, and Gemini invocation; normalized result envelope |
| Verifier | `router/verify.py` | Deterministic checks, review parsing, and acceptance decision |
| Schemas | `router/*.schema.json` | Contract and verdict structure; validated by the included subset validator |
| Policy | `router/policy.json` | Roles, model catalog, tiers, limits, and reviewer preference |
| Governance generator | `router/generate.py` | `CLAUDE.md`, `AGENTS.md`, `CROSS-DOMAIN.md`, and Claude tool-deny settings |
| Publication gate | `gate/publish-gate.sh` | Marker scan of a tree, index blobs, or changed blobs across a revision range |
| Scan wrapper | `gate/publish-check.sh` | File, stdin, and textual-diff scans |
| Hook installer | `gate/install-hooks.sh` | Pre-commit and pre-push hooks calling the gate |
| Registry | `registry/generate.py` | `registry.json` and `REGISTRY.md` with configuration and dated observations |
| Registry audit | `ops/registry-audit.sh` | Snapshot, refresh, diff, and issue count |
| Status renderer | `ops/cockpit.sh` | Hub `STATUS.md` and notifications when its attention list changes |
| Session handoff | `ops/session-handoff.sh` | Dated workspace snapshot and next task |
| Vendor handoff | `ops/handoff-to-vendor.sh` | Handoff file and a command to start another vendor manually |
| Coordination | `coordination/PROTOCOL.md` | Ownership, evidence, and handoff conventions |
| Claude integrations | `skills/wrap/`, `agents/` | Session wrap-up, marker scanning, and registry audit instructions |

## Common commands

Run these from the checkout:

```bash
make test
make lint
make generate
make drift-check
make registry
make audit
make cockpit
```

`test` is offline. `registry` and `audit` inspect local configuration and may run configured external probes. `cockpit` reads the registry snapshot, checks local state, and runs the test and drift checks. It does not refresh every registry probe.

The core router requires its Python files, policy, schemas, and a governance file. The generator and `ai init` also use `shared/governance.example.json`. The gate can be used separately with a marker file. The ops scripts assume the `<hub>/_system` layout.

See [usage](usage.md) for CLI commands, [configuration](configuration.md) for settings, and [architecture](architecture.md) for enforcement limits.
