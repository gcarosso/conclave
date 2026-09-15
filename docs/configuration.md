# Configuration

| File | Purpose | Git status |
|---|---|---|
| `shared/governance.json` | Operator, hub path, domains, vendor eligibility, and generated rules | Ignored; copy supplied example or run `ai init` |
| `router/policy.json` | Roles, models, tiers, limits, and review configuration | Tracked; preserve local edits during upgrades |
| `gate/markers.txt` | Publication scan patterns | Ignored; copy `markers.example.txt` |
| `registry/config.json` | Optional inventory probes | Ignored; copy `config.example.json` |
| `registry/manual.json` | Dated observations that cannot be probed | Ignored; copy `manual.example.json` |

## Governance

Start from [governance.example.json](../shared/governance.example.json). `hub` defaults to the checkout's parent directory when null. Domain entries specify `kind`, `default_data_class`, and `title`; optional fields include `vendors`, `notes`, and `canary`.

Eligible vendors are the intersection of the domain's vendor list and the selected data class's vendor list. A domain without its own list inherits the hub's `vendors`. The example permits Claude and Codex for private content; wider routing requires an explicit classification decision.

`rules` supplies the text rendered into `CROSS-DOMAIN.md`. The generator also writes root and domain `CLAUDE.md`/`AGENTS.md` files and Claude file-tool deny settings for sibling domains.

```bash
make generate
make drift-check
```

Generated settings are not an OS isolation boundary. Review their behavior against the installed client; see [enforcement](architecture.md#enforcement-boundary).

## Routing policy

A role defines a default vendor and tier, a review flag, a turn limit, and `codex_sandbox`. Optional `hub_only` roles are refused outside `_system`.

- `models`: allowed IDs, vendor, tier, configured availability, and `requires_approval`.
- `ladders`: a model ID for each vendor/tier combination. Multiple tiers may map to one model.
- `timeouts_s`: per-tier defaults, copied into a job's per-call timeout when the contract is built.
- `limits`: normal-job call budget, permitted repairs, escalation switch/count, and review character limit. Current execution performs at most one escalation.
- `reviewer_for`: preferred reviewing vendor; fallback remains subject to eligibility, availability, approval, and remaining budget.
- `council`: two configured member vendors and tiers, plus the judge vendor and tier.

The shipped limits are six adapter calls, one repair, one escalation, and 80,000 review characters. The timeout remains the contract's initial value during repair and escalation. Consensus records a separate ceiling of two calls per requested sample, allowing one malformed-response retry.

The executable model gate is `models[].requires_approval`. Keep `governance.top_model_gate.models` consistent; that list drives generated instructions. Model IDs and availability flags are examples to verify against your accounts. `ai smoke` tests only tier-1 entries and does not update policy or registry files.

## Marker files

Use one POSIX extended regex per line. Matching is case-insensitive; blank lines and lines starting with `#` after whitespace are ignored. Patterns should cover identifiers relevant to the material you publish. The example includes common path and key patterns, not an exhaustive secret catalog.

Resolution order:

1. `--markers FILE`
2. `PUBLISH_GATE_MARKERS`
3. `<target>/.publish-gate-markers`
4. `<checkout>/gate/markers.txt`

A named file that is missing, empty, or invalid blocks the scan. Exact-line exceptions belong in `<target>/.publish-gate-allow` after review. Finding format is consistent across modes: `path:line:text` or the printed binary finding. Old exceptions beginning with `+` from textual-diff scans must be regenerated.

## Registry

`registry/config.json` can set `launchd_prefixes`, enable Composio connection probing, and add `extra_commands` with a name and an argument list or shell-like string. Strings are split into arguments; the probe does not execute a shell pipeline.

The registry combines observations and configuration. CLI versions, SDK importability, configured MCP servers, and model catalog entries are different kinds of evidence. Model entries are copied from policy, and the router does not use registry results for routing. Keep generated registry output private because it can contain local paths and configuration details.

## Environment

| Variable | Effect |
|---|---|
| `AI_GOVERNANCE` | Override the governance file for the router and generator |
| `AI_POLICY` | Override router policy |
| `AI_NO_COCKPIT=1` | Suppress automatic status refresh |
| `COCKPIT_NOTIFY=0` | Disable status-change notifications |
| `PUBLISH_GATE_MARKERS` | Select a marker file |
| `GEMINI_API_KEY` | Gemini credential; adapter also checks a login shell if unset |
| `PREFIX` | Installer prefix; defaults to `~/.local` |

Ops and registry scripts read configuration relative to the checkout. `AI_GOVERNANCE` and `AI_POLICY` are not global overrides for every component.
