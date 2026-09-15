# Conclave

![CI](https://github.com/gcarosso/conclave/actions/workflows/ci.yml/badge.svg)

**A multi-vendor AI job router where "done" is a verdict, not an exit code.** One command sends a task to the cheapest adequate model from Claude, Codex, Grok or Gemini; a contract says what "done" means; a fresh-context reviewer from a *different* vendor judges the result; the kernel, not the worker, writes the acceptance. Around the router: a governance file that generates every vendor's instruction files, a fail-closed publish gate, a capability registry, and a one-glance cockpit. Standard-library Python and Bash, no dependencies, everything testable offline.

Built by [Giovanni Carosso](https://gcarosso.bio). Part of the tools at [gcarosso.bio/tools](https://gcarosso.bio/tools/).

```bash
mkdir -p ~/hub && cd ~/hub
git clone https://github.com/gcarosso/conclave _system
_system/install.sh --init          # links `ai`, writes governance.json, creates domain folders, generates instruction files
ai smoke                            # tier-1 ping of every vendor you have installed
cd work && ai scout "List the three largest files here, one line each on what they are"
```

```
Orchestration: scout claude/claude-haiku-4-5-20251001
  · attempt 1 succeeded → pass
1. notes/2026-plan.md — 41 KB, the quarterly plan …
2. …

Acceptance: PASS · ~/hub/work/.ai/jobs/20260914T231501Z-scout
```

The first line says who did the work. The last line says whether it passed the checks the contract declared, and where the full record is: contract, every attempt, the reviewer's verdict, the acceptance. Exit 0 means the checks passed. Nothing else does.

## Why

Every agent framework can call a model. The hard part is what happens around the call:

- **"It said it worked" is not evidence.** A process that exits 0 with a fluent refusal, a partial result, or a confident wrong answer is logged as success by most tools. Conclave separates `execution_status` (did the process run) from `acceptance_status` (did the declared checks pass), and only the second one is allowed to say PASS.
- **A model reviewing its own work mostly agrees with itself.** Conclave's reviewer is a different vendor with fresh context and no access to the writer's reasoning. It returns a structured verdict with evidence, and the router uses that verdict to drive one bounded repair and, only when the reviewer says a stronger model is needed, one gated escalation.
- **Private material should not reach every model you happen to have a key for.** Every domain has a data class; every data class names the vendors allowed to see it; prompt-only vendors run from an empty sandbox no matter what. Declassifying a payload for one task is a recorded decision in the job contract, not a message.
- **Rules that live in five files drift.** One `governance.json` generates the cross-domain rules, each vendor's instruction file, and Claude Code's deny rules. A drift check tells you when someone hand-edited a generated file.
- **Public repos leak by accident, never on purpose.** The publish gate scans trees, staged changes and push ranges for the markers you list, including inside binaries and dotfiles, and blocks on any scan error. It fails closed.
- **The expensive model is not the trustworthy one.** Routing goes by role and tier: cheap models for lookups, the workhorse for real work, the top model only with per-use approval that is written into the contract. Cost control and audit trail in one mechanism.

## The tools

| Tool | What it does | Reasoning method | What it buys you |
|---|---|---|---|
| **`ai <role>`** — the router kernel | Routes one task by role, tier and data class; runs it; verifies; accepts | Contract-first execution: goal → declared checks → verdict, with the worker never awarding its own PASS | Reproducible, auditable jobs; smallest adequate model by default; vendor portability |
| **Cross-vendor review** | A fresh-context reviewer from another vendor judges the artifact against the contract's checks | Independent verification: no sunk-cost bias, and a different model family decorrelates errors | Catches what self-review misses; structured issues with evidence and a fix |
| **Bounded repair + gated escalation** | One repair on the reviewer's issues; one tier escalation only on `capability_deficit`, behind the approval gate | Iterative refinement with explicit stop conditions; escalate on evidence, not on failure | No runaway loops or costs; top models used only when a reviewer says why |
| **`ai auto`** | One tier-1 call classifies role, tier and review need, then runs the job | Scout-then-specialist: cheap classification before expensive execution | Right-sized routing without the user knowing the roles |
| **`ai council`** | Two independent mid-tier advisors; a top-model judge only if they disagree | Jury-then-judge: parallel independent judgment, adjudication on disagreement only | Cheap when they agree, strong when they don't; no anchoring between members |
| **`ai consensus`** | N cheap samples with rotating framings and vendors, aggregated mechanically into mode, splits and outliers | Stochastic ensemble / polling: the mode filters noise, splits reveal judgment calls, outliers surface ideas | Breadth for the price of tier-1 calls; a poll, explicitly never a verdict |
| **Contract and verdict schemas** | Machine-validated job contracts (goal, scope, writer, effects, authorization, limits, checks) and verdicts | Specification as data: the reviewer has something concrete to reject | Authorization and acceptance are inspectable state, not prose |
| **Governance generator** | One JSON file → cross-domain rules, per-vendor instruction files, Claude Code deny rules; drift check | Single source of truth with generated surfaces | Every vendor reads materially the same rules; hand edits are detected |
| **Data classes + sandboxing** | Eligibility = domain vendors ∩ data-class vendors; prompt-only vendors always run in an empty directory | Least context / need-to-know | Private data reaches only vendors you cleared; declassification is recorded |
| **Top-model gate** | Per-use approval for gated models, recorded in the contract | Human-in-the-loop on cost and capability | No silent use of expensive models; an audit trail of who approved what |
| **Writer lock** | One writer per write set, enforced with an exclusive lock file | Mutual exclusion for agents | Concurrent agents never produce a merge instead of a result |
| **Publish gate** | Fail-closed marker scanner for trees, staged changes and push ranges; git hooks | Boundary control that blocks on error, not only on findings | Private markers cannot cross into public repos, even via binaries or history |
| **Registry** | Probes vendor CLIs, MCP servers, skills, scheduled jobs and models; JSON first, Markdown view | Observed state over declared state | Routing and troubleshooting use verified capabilities; failures are recorded, never omitted |
| **Cockpit** | Renders `STATUS.md` with an attention list derived from the facts; notifies only on change | Derived attention: facts → conditions → delta | One glance says what needs you |
| **Job files as protocol** | Durable on-disk state, handoff scripts, the `/wrap` skill | Coordination through artifacts, not conversation | Any vendor resumes any job; evidence survives context loss |

The full catalog with commands, file locations and design rationale is in [docs/tools.md](docs/tools.md). The methodology behind each mechanism is in [docs/concepts.md](docs/concepts.md).

## Layout

Conclave is meant to be checked out as the `_system/` directory of a **hub**: a folder whose subfolders are your **domains**, each one a context envelope a session works in.

```
~/hub/
  work/  personal/  …        your private domains — one session works in one
  public/                     public repos — treated as already published
  _publishing/                private staging on the way to public/
  _system/                    ← this repository
    router/    ai · kernel.py · adapters.py · verify.py · generate.py · policy.json · schemas · tests.py
    shared/    governance.json (yours, generated from governance.example.json)
    gate/      publish-gate.sh · markers.txt · install-hooks.sh · tests/
    registry/  generate.py · config.json · registry.json → REGISTRY.md
    ops/       cockpit.sh · session-handoff.sh · handoff-to-vendor.sh · registry-audit.sh
    coordination/PROTOCOL.md · skills/wrap · agents/
  CROSS-DOMAIN.md  CLAUDE.md  AGENTS.md  STATUS.md      generated / rendered
```

You can also vendor just `router/` into anything: it is four Python files with no imports outside the standard library.

## Documentation

| | |
|---|---|
| [docs/install.md](docs/install.md) | Prerequisites, install, bootstrapping a hub, setting up each vendor, verifying, hooks |
| [docs/usage.md](docs/usage.md) | Daily workflow, every command and flag, prompts that work, reading a job folder, publishing |
| [docs/concepts.md](docs/concepts.md) | The reasoning methodology: why each mechanism exists and what it confers |
| [docs/tools.md](docs/tools.md) | The catalog: every tool classified, with commands, files, and bundling rationale |
| [docs/configuration.md](docs/configuration.md) | `governance.json`, `policy.json`, markers, registry config, environment variables |
| [docs/architecture.md](docs/architecture.md) | How a job flows, job-folder anatomy, the honest enforcement boundary, extending |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Symptoms and first moves |

## What it is not

- Not an agent framework or an SDK. It drives the vendor CLIs you already log into (`claude`, `codex`, `grok`) and the Gemini SDK, and writes files. There is no server, no daemon, no database.
- Not a guarantee of isolation beyond what it says. The router enforces eligibility, data class, the model allowlist, the approval gate, timeouts, the writer lock and acceptance for everything launched through `ai`. A desktop chat or a raw vendor CLI in the same shell is governed by the generated instruction files only. Claude Code's deny rules are technical; other vendors' read confinement is behavioral. [docs/architecture.md](docs/architecture.md#enforcement-boundary) states exactly which is which.
- Not tied to the model ids in `policy.json`. They are an allowlist you edit; `ai smoke` re-verifies them.

## Requirements

Python 3.9+, Bash 3.2+, git. macOS or Linux. Vendor CLIs are optional individually: a vendor you don't install is simply never routed to.

## License

Apache 2.0. See [LICENSE](LICENSE).
