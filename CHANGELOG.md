# Changelog

## 0.1.0 — first public release

Extracted from a private multi-vendor hub and made generic.

- Router: `ai <role>` with contracts, deterministic checks, fresh-context cross-vendor review, bounded repair, gated escalation, one writer per write set, per-job audit trail.
- `ai auto` (triage), `ai council` (two advisors + gated judge), `ai consensus` (stochastic ensemble), `ai accept`, `ai smoke`, `ai jobs`, `ai roles`, `ai init`.
- Governance generator: one JSON file → cross-domain rules, per-vendor instruction files, Claude Code deny rules; drift check.
- Publish gate: fail-closed private-marker scanner (tree / staged / push-range), markers file, allowlist, hook installer, 22 fixtures.
- Registry: probe-based capability inventory (JSON first, Markdown view).
- Ops: cockpit (STATUS.md with derived attention), session handoff, vendor handoff, registry audit.
- Coordination protocol, `/wrap` skill, Claude Code agent definitions.
- 47 offline router tests; CI on Linux and macOS, Python 3.9+.
