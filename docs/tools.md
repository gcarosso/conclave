# Tool catalog

Every tool in the package, classified by function and reasoning method, with the advantage it confers, where it lives, and how you run it. The bundling rationale is at the end.

Legend for **Method**: the reasoning or control pattern the tool implements (see [concepts.md](concepts.md) for the full explanation of each).

---

## A. The router (core)

### `ai <role> "task"` — route, run, verify, accept

| | |
|---|---|
| **Function** | Turns a task into a contract, picks (vendor, model, tier) by role and data class, runs the vendor, evaluates the checks, writes the verdict and acceptance. |
| **Method** | Contract-first execution · capability-fit routing · verdicts over exit codes |
| **Advantage** | Reproducible, auditable jobs. The smallest adequate model by default. "Done" means the declared checks passed. |
| **Files** | `router/ai` (CLI), `router/kernel.py` (contract, routing, locks, job state, repair/escalation), `router/verify.py` (checks, review, acceptance), `router/adapters.py` (vendor transports), `router/policy.json`, `router/contract.schema.json`, `router/verdict.schema.json` |
| **Run** | `cd <hub>/<domain> && ai scout "…"` · roles: `ai roles` · flags: `--vendor --model --tier --max-tier --data-class --approve-top-model --review/--no-review --dry-run --json --source` |
| **Output** | First line `Orchestration: <role> <vendor>/<model>`; last line `Acceptance: PASS|FAIL|BLOCKED · <job dir>`; exit 0 only on PASS |

### Cross-vendor review (a `review` check)

| | |
|---|---|
| **Function** | A fresh-context reviewer from a different vendor judges the artifact against the contract's review checks and returns per-check status with evidence plus issues. |
| **Method** | Independent verification (fresh eyes, different model family) |
| **Advantage** | Catches what self-review misses; issues arrive structured, with severity, a fix, and a `capability_deficit` flag that drives escalation. |
| **Files** | `router/verify.py` (`REVIEW_PROMPT`, `REVIEW_OUTPUT_SCHEMA`, `evaluate`), `router/kernel.py` (`reviewer_callable`), `policy.json` → `reviewer_for` |
| **Run** | On by default for `write` and `code`; force with `--review`, skip with `--no-review` |

### Bounded repair and gated escalation

| | |
|---|---|
| **Function** | One repair attempt fed with the reviewer's issues; one tier escalation only when an issue is marked `capability_deficit`, passing through the approval gate. |
| **Method** | Iterative refinement with explicit stop conditions; escalate on evidence |
| **Advantage** | No runaway loops; top models only when a reviewer says why; every step is an event. |
| **Files** | `router/kernel.py` (`run_job`), `policy.json` → `limits.repairs`, `limits.escalations`, `limits.calls` |

### `ai auto "task"` — triage

| | |
|---|---|
| **Function** | One tier-1 classification call returns `{role, tier, review}`; the job then runs normally with those settings. |
| **Method** | Scout-then-specialist |
| **Advantage** | Right-sized routing for users who don't want to learn the roles; a proper contract and verdict regardless. |
| **Files** | `router/kernel.py` (`triage`, `TRIAGE_PROMPT`, `TRIAGE_SCHEMA`) |

### `ai council "question"` — two advisors, judge on disagreement

| | |
|---|---|
| **Function** | Two mid-tier vendors answer independently as JSON; if they disagree or raise objections, a gated tier-3 judge resolves the dispute. |
| **Method** | Jury-then-judge; independence removes anchoring |
| **Advantage** | Cheap when they agree, strong when they don't; the whole exchange is on disk. |
| **Files** | `router/kernel.py` (`council`, `COUNCIL_PROMPT`, `JUDGE_PROMPT`), `policy.json` → `council` |
| **Output** | `Council: AGREE|JUDGED|DISAGREE|BLOCKED · <job dir>`; exit 0 on AGREE or JUDGED |

### `ai consensus "question" [--n 5] [--options "A;B"]` — stochastic ensemble

| | |
|---|---|
| **Function** | N parallel tier-1 samples with rotating framings and vendors; mechanical aggregation into mode, splits, outliers. |
| **Method** | Polling / stochastic ensemble with framing diversity |
| **Advantage** | Breadth for tier-1 prices; a labelled poll, never a verdict. |
| **Files** | `router/kernel.py` (`consensus`, `FRAMINGS`, `CONSENSUS_PROMPT`) |
| **Output** | `Consensus: CONSENSUS|SPLIT|BLOCKED · valid/N · <job dir>`; exit 0 on CONSENSUS (mode ≥ 60%) |

### `ai accept <job-dir>` — re-run deterministic checks

Re-evaluates a job's `builtin` and `command` checks against its `result.md` and rewrites the verdict. Useful after you fixed something by hand and want the record to say so.

### `ai smoke` · `ai jobs` · `ai roles` · `ai init` · `ai version`

| Command | What |
|---|---|
| `ai smoke` | Tier-1 "reply SMOKE_OK" ping per vendor from an empty temp dir; exit 0 only if all pass. Re-verifies the model allowlist. |
| `ai jobs` | Last 15 jobs with acceptance status, domain, role, job dir. |
| `ai roles` | Every role with description, default vendor/tier. |
| `ai init [--hub DIR] [--force]` | Writes `shared/governance.json` from the example, creates domain folders and canaries, generates instruction files. |
| `ai version` | Prints the version. |

---

## B. Governance

### Governance generator — `router/generate.py`

| | |
|---|---|
| **Function** | Renders `CROSS-DOMAIN.md`, hub-root and per-domain `CLAUDE.md`/`AGENTS.md`, and per-domain `.claude/settings.json` deny rules from `shared/governance.json`. `--check` reports drift, exit 1 if any. |
| **Method** | Single source of truth, generated surfaces |
| **Advantage** | Every vendor reads materially the same rules; hand edits are detected; Claude Code gets technical isolation. |
| **Run** | `make generate` after editing governance; `make drift-check` in CI or the cockpit |

### Data classes, eligibility, sandboxing

| | |
|---|---|
| **Function** | `eligible = domain.vendors ∩ data_class.vendors`; `--data-class` above the domain default records a declassification in the contract; prompt-only vendors always run in an empty sandbox. |
| **Method** | Least context / need-to-know, recorded decisions |
| **Files** | `shared/governance.json` (`data_classes`, `domains[].vendors`), `router/kernel.py` (`eligible_vendors`, `attempt`), `router/adapters.py` (`PROMPT_ONLY_VENDORS`) |

### Top-model gate

| | |
|---|---|
| **Function** | Models with `requires_approval` need `--approve-top-model` or an interactive yes; the record lands in `contract.authorization.top_model_approval`. |
| **Method** | Human-in-the-loop on cost and capability |
| **Files** | `policy.json` (`models[].requires_approval`), `governance.json` (`top_model_gate`), `router/kernel.py` (`gate_check`) |

### Writer lock

| | |
|---|---|
| **Function** | One running job per write set, via an `O_EXCL` lock keyed on the sorted write paths; stale locks reclaimed. |
| **Method** | Mutual exclusion |
| **Files** | `router/kernel.py` (`acquire_writer_lock`), `<domain>/.ai/jobs/locks/` |

---

## C. Publication safety

### Publish gate — `gate/publish-gate.sh`

| | |
|---|---|
| **Function** | Scans a tree (`<path>`), the staged index (`--staged <repo>`), or a push range (`--diff <repo> [A..B]`) for extended-regex markers; binaries via `strings`; dotfiles included; allowlist of exact lines. Any scan/git error blocks. Missing markers file blocks. |
| **Method** | Fail-closed boundary control |
| **Advantage** | Private markers cannot cross into public repos, at commit or push, even in binaries or history. |
| **Files** | `gate/publish-gate.sh`, `gate/markers.txt` (yours; `markers.example.txt` shipped), `.publish-gate-markers` / `.publish-gate-allow` per repo, `gate/tests/gate-test.sh` (22 fixtures) |
| **Run** | `gate/publish-gate.sh <repo>` · hooks: `gate/install-hooks.sh <repo>…` · wrapper for files/stdin: `gate/publish-check.sh` |

---

## D. Observability

### Registry — `registry/generate.py`

| | |
|---|---|
| **Function** | Probes vendor CLIs, MCP servers, skills, agents, scheduled jobs, the Gemini key and SDK, and copies the model catalog with gate flags. Writes `registry.json` (source) and `REGISTRY.md` (view). `--probe` prints without writing. |
| **Method** | Observed state over declared state |
| **Run** | `make registry` · audit (snapshot → refresh → diff → issue count): `make audit` |
| **Config** | `registry/config.json` (`launchd_prefixes`, `probe_composio`, `extra_commands`), `registry/manual.json` for non-enumerable facts with `last_verified` |

### Cockpit — `ops/cockpit.sh`

| | |
|---|---|
| **Function** | Renders `<hub>/STATUS.md`: attention list, scheduled jobs, vendors, router health (tests, drift, gate fixtures), recent jobs, public repos, open items. Runs automatically after every `ai` job; notifies on change. |
| **Method** | Derived attention |
| **Run** | `make cockpit` · disable auto-refresh with `AI_NO_COCKPIT=1`, notifications with `COCKPIT_NOTIFY=0` |

---

## E. Coordination

### Job files as protocol — `coordination/PROTOCOL.md`

The rules by which any vendor picks up any job: read `acceptance.json` first, one writer, authorization never expands by message, evidence over claims.

### Handoffs — `ops/session-handoff.sh`, `ops/handoff-to-vendor.sh`, `skills/wrap`

| Tool | What |
|---|---|
| `ops/session-handoff.sh [--task "…"]` | Writes `handoffs/<UTC>-handoff.md`: domains, router state, last five jobs with acceptance, public-repo git status, environment. |
| `ops/handoff-to-vendor.sh <claude\|codex> "task"` | The failover: writes a handoff and prints the exact command that puts the other vendor's top model in the coordinator seat with the same rules. |
| `skills/wrap/SKILL.md` | A Claude Code skill: `/wrap` inventories the session (verified, not recalled), writes the handoff, runs pre-archive checks; `/wrap archive` archives only if every check passes. |
| `agents/*.md` | Claude Code subagent definitions for the publish check and the registry audit. |

---

## Bundling: why one repository

The tools share their configuration (`governance.json`, `policy.json`), call each other (the kernel refreshes the cockpit; the cockpit runs the tests, the drift check and the gate fixtures; the registry reads the policy; the handoff scripts read the ladders), and are meant to be installed as one directory (`<hub>/_system`). Splitting them would force every user to wire four repositories to the same files. So:

- **One repo, layered by directory.** `router/` is the core and has no dependency on anything else in the package: four standard-library Python files you can vendor on their own. `gate/`, `registry/`, `ops/`, `coordination/`, `skills/`, `agents/` are optional modules; ignore a directory and nothing breaks (the kernel skips the cockpit if `ops/cockpit.sh` is absent; the cockpit degrades gracefully when the registry or gate is absent).
- **One config surface per concern.** Rules and domains in `shared/governance.json`; roles, models, ladders and limits in `router/policy.json`; markers in `gate/markers.txt`; probe options in `registry/config.json`. Each has a shipped `*.example.*` and each real file is gitignored.
- **One test command.** `make test` runs the router suite (fake vendor, temp hub) and the gate fixtures, offline, in under a second. CI runs the same plus a full `ai init` → `drift-check` → dry-run cycle on Linux and macOS.
- **One version.** The CLI, the schemas and the docs move together; `CHANGELOG.md` is the record.

What is deliberately **not** in the package: anything specific to one person's hub (their domain names, markers, scheduled jobs, publication pipelines), and any third-party prompt packs or course material that inspired the patterns. The patterns are credited in [concepts.md](concepts.md#where-these-come-from); the code is original.
