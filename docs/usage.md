# Usage

Run domain work from `<hub>/<domain>`. The CLI infers the domain from the working directory; use `--domain` outside the hub. Hub-root jobs use `_system`.

For choosing between one model, delegated tasks, review, and council, see [multi-agent workflows](workflows.md). A lead assistant session with shell access can invoke these commands and use job records to coordinate the next step.

## Task commands

| Command | Default behavior |
|---|---|
| `ai scout "task"` | Tier 1; nonempty-response check |
| `ai plan "task"` | Tier 2; planning prompt, no review |
| `ai code "task"` | Tier 2; Codex writer and cross-vendor review |
| `ai write "task"` | Tier 2; Claude writer and cross-vendor review |
| `ai review "target"` | Tier 2; review prompt and read-only Codex sandbox |
| `ai live "question"` | Grok web search; requires an eligible data class |
| `ai longdoc "task"` | Tier-2 document analysis |
| `ai auto "task"` | Tier-1 classification, then a normal job |

`ai roles` lists all roles, including the configurable knowledge-base roles. The default `nonempty` check requires more than 20 characters after trimming outer whitespace.

```bash
ai scout "List the three most recently modified files under notes/ and summarize each"
ai code "Fix duplicate-ID handling in src/process.py. Run the relevant tests and report their exit status."
ai write "Edit docs/summary.md for an ML engineer. Keep names, numbers, and uncertainty; stay under 120 words."
ai review "Review src/process.py for incorrect deduplication. Cite file and line."
```

Name the inputs, permitted edits, expected output, and useful evidence. These instructions guide the model and reviewer. The CLI does not turn a named test command or word limit into an executable check, and it does not narrow a domain-wide write set from prompt text. Use the kernel API for explicit checks; verify repository changes separately.

## Flags

| Flag | Effect |
|---|---|
| `--vendor V` / `--model M` | Select an eligible vendor or an available model in the catalog |
| `--tier N` / `--max-tier N` | Select or cap tiers 1–3 for the standard job; an explicit model above the cap is refused |
| `--data-class private\|sanitized\|public` | Set payload classification; widening from the domain default records declassification |
| `--approve-top-model` | Record approval for a gated model; otherwise interactive runs ask and noninteractive runs refuse |
| `--review` / `--no-review` | Enable or omit cross-vendor response review |
| `--dry-run` | Print a route preview without calling a vendor or writing a job |
| `--json` | Return structured output for standard role jobs |
| `--source "reason"` | Record the source of authorization |
| `--domain D` | Select the configured domain |

For `auto --dry-run`, classification is skipped because it requires a model call; use an explicit role to inspect a concrete route. Council and consensus use their own configured models and output formats; role-routing flags and `--json` do not configure those subcommands.

`--data-class sanitized` records your classification. It does not redact the prompt or change which files a local CLI can read.

## Job records

Standard jobs write `<domain>/.ai/jobs/<id>/`; hub jobs use `_system/router/jobs/<id>/`.

```text
contract.json              goal, scope, authorization, limits, and checks
events.jsonl               dispatch, result, fallback, and decision events
attempts/
  1/                       first writer call
    request.json           model, working directory, purpose, and prompt
    result.json            execution status, timing, usage, and errors
    result.md              returned text
    stdout.txt, stderr.txt raw client output
    review-raw.txt         review response, when requested
  1-review-codex/           separate reviewer record
  2/                       repair or escalation
result.md                  current/final returned text
verdict.json               check results, evidence, issues, and response hash
acceptance.json            final acceptance and writer-attempt summary
```

Read `acceptance.json`, then `verdict.json` and `result.md`. Inspect `events.jsonl` and attempt directories for dispatch and review details. Usage is recorded when clients report it; missing cost is `null`.

| Status | Meaning |
|---|---|
| `pass` | All declared checks passed |
| `fail` | At least one check failed |
| `blocked` | Execution or evaluation could not complete, including unavailable review or exhausted call budget |

For standard jobs, exit 0 means `pass`, exit 1 means `fail` or `blocked`, and exit 2 reports a CLI or routing error. These records support downstream decisions; the package has no dependency scheduler.

`ai accept <job-dir>` re-evaluates builtins and command checks against `result.md` and overwrites the final verdict. Review checks become blocked because this command does not call a reviewer. Preserve the existing record before manual re-evaluation if its history matters.

## Council and consensus

```bash
ai council "Should this pipeline use a queue or a synchronous worker? Compare failure recovery and operational cost."
ai consensus "How should a scanner handle an unreadable file?" --options "block;warn;continue" --n 5
```

Council requests two separate recommendations. Exact agreement after case normalization, with no objections, returns `agree`; otherwise an approved judge can return `judged`. Missing answers return `blocked`, and unresolved disagreement returns `disagree`. Exit 0 means `agree` or `judged`.

Consensus runs 3–10 samples, with up to five concurrent calls and one retry for a malformed successful response. It reports `consensus` when at least `max(3, floor(n/2))` samples are valid and the mode has at least 60% of valid responses; otherwise it reports `split` or `blocked`. Exit 0 means `consensus`. Confidence is model-reported. Neither subcommand writes a standard acceptance verdict.

## Publication scans

Prepare the material in its source or staging directory. From the hub, scan that material, copy it into the public repo, then scan the destination and index:

```bash
_system/gate/publish-gate.sh _publishing/prepared-package
_system/gate/publish-gate.sh public/example-repo
_system/gate/publish-gate.sh --staged public/example-repo
```

Installed hooks repeat the index and push-range checks. Resolve findings and scan errors before continuing. `publish-check.sh --file FILE` and `--stdin` support individual inputs; its `--diff` option scans a textual diff and cannot inspect binary Git blobs. Use the gate's repository modes for publication.

## Status and handoffs

- `ai jobs`: recent jobs; `?` means no standard acceptance record, including council and consensus.
- `make cockpit`: render `STATUS.md` from the registry snapshot and local checks. Notifications occur when the attention list changes.
- `ops/session-handoff.sh --task "next step"`: write a dated handoff.
- `ops/handoff-to-vendor.sh --approve-top-model codex "next step"`: prepare a handoff and print a direct CLI command. This does not launch the next session or create a router job.

Read the specific handoff file on the next session. The `/wrap` skill adds ownership, evidence, and archive checks. [Coordination protocol](../coordination/PROTOCOL.md).
