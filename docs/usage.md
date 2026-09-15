# Usage

How to work with Conclave day to day: where to start a session, which command to reach for, how to write a task that gets a verdict you can trust, and how to read what comes back.

## Where to start a session

| You want to… | Start here | Why |
|---|---|---|
| Do work in one area (a project, your notes, a repo) | `cd <hub>/<domain>` | Instruction files and deny rules are per domain; the router detects the domain from your directory. |
| Publish something to a public repo | The hub root, on your own instruction | Domain sessions are blocked from public domains by design. Publishing is a deliberate act, not a side effect. |
| Change rules, roles, models, schedules | The hub root | `_system` is administration. |

Don't run domain work from the hub root: you would be trading isolation for convenience. Outside the hub entirely, `ai` needs `--domain`.

## Picking the command

| Command | Use it when | What actually happens |
|---|---|---|
| `ai auto "task"` | You don't know what it needs | One tier-1 call picks role, tier and review; then the job runs. |
| `ai scout "q"` | A lookup, a triage, a quick answer | Cheapest model, no review. |
| `ai plan "…"` | Architecture, strategy, multi-document analysis | Tier 2, no review by default. |
| `ai write "…"` / `ai code "…"` | Real deliverables | Tier 2; a fresh-context reviewer from another vendor; one repair; a verdict. |
| `ai review "target"` | Someone else's output | Read-only; never edits. |
| `ai live "q"` | Needs today's web | Grok with web search, from an empty sandbox. |
| `ai longdoc "…"` | Very long reading | Tier 2, higher turn budget. |
| `ai council "q"` | A decision with two defensible sides | Two mid-tier vendors; a gated top-model judge only if they disagree. |
| `ai consensus "q" --options "A;B"` | You want a poll, not a verdict | Five cheap samples across vendors → mode, splits, outliers. |
| `ai jobs` · `ai smoke` | Cockpit | Recent verdicts · are all vendors alive. |

`ai roles` lists every role with its defaults. The knowledge-base roles (`ingest`, `compile`, `ask`, `file-back`, `lint`) are tier-1 roles for wiki-style workflows; keep, rename or delete them in `policy.json`.

### Flags

| Flag | Effect |
|---|---|
| `--vendor V` / `--model M` | Force a vendor or a specific model id (must be in the allowlist and eligible for the data class). |
| `--tier N` / `--max-tier N` | Force or cap the tier. |
| `--data-class sanitized\|public` | Raise the payload's class for this job; the declassification is recorded in the contract. |
| `--approve-top-model` | Pre-approve a gated model (needed in scripts; interactive runs prompt). |
| `--review` / `--no-review` | Force or skip the cross-vendor review. |
| `--dry-run` | Print the route, the checks, the timeout; execute nothing, write nothing. |
| `--json` | Machine-readable output: header, acceptance, job dir, text, attempts, checks, issues. |
| `--source "…"` | Why this job is authorized; lands in `contract.authorization.source`. |
| `--domain D` | Override domain detection (required outside the hub). |

Use `--dry-run` liberally. It is the fastest way to see why a vendor is refused or which model would run.

## Prompts that work here

The router turns your ask into a contract: **goal → checks → verdict**. A prompt that names the goal, the evidence of done, and the boundaries gets a verdict you can trust. One that says "improve this" gets a fluent guess.

**The shape:** *what* (one sentence) · *done means* (something checkable) · *don't* (the boundary) · *inputs* (which files).

| Weak | Strong | Why the strong one works |
|---|---|---|
| `ai scout "what's in this folder"` | `ai scout "List the three most recently modified files under notes/ with one line each on what changed"` | Bounded output; the model can't pad. |
| `ai write "improve my summary"` | `ai write "Rewrite docs/summary.md for a technical reader. Done means: ≤120 words, keeps every date and name, states 3 quantified outcomes. Don't invent numbers."` | Goal, checks, boundary. The reviewer has something to reject. |
| `ai code "fix the tests"` | `ai code "tests/test_process.py::test_dedup fails on duplicate ids. Fix in src/process.py only; run pytest -q tests and report the exit code. Don't change test files."` | Located failure, a write set, a command check the kernel can run. |
| `ai plan "should we move to Postgres"` | `ai plan "We store ~2M rows in SQLite, single writer, nightly rebuild. Recommend stay/move with the one decisive constraint, migration cost in days, and what would change the answer."` | Facts up front, decision-shaped output, a falsifier. |
| `ai live "industry news"` | `ai live "Since 1 Sep: product launches, deals ≥$1B, and regulatory updates in <field>. Table: date · item · number · URL. Say what you couldn't verify."` | Dated window, table schema, explicit unknowns column. |
| `ai review "check this"` | `ai review "Review build/index.html for XSS in the search box and for any private path or email string. Cite file:line. Do not edit."` | Named risks, evidence format, read-only. |
| `ai council "is the thesis good"` | `ai council "Should we fund a prototype before a validation study, or the reverse? Judge on time-to-first-evidence and capital at risk."` | Two defensible sides, one rubric. |
| `ai consensus "what should I do"` | `ai consensus --options "fail closed;fail open;warn only" "A publish gate hits a scanner error. What should it do?"` | Fixed options make the poll aggregable. |
| `ai auto "the site is slow"` | `ai auto "Home page takes 4 s on mobile (Lighthouse report in notes/perf.md). Find the top cause."` | Auto-triage still needs a symptom and a location. |

**Patterns to reuse**

- *Done means …* turns a wish into a check. If you can't write it, the task isn't ready.
- *Only in … / Don't …* is the boundary; it becomes the write set and keeps the reviewer honest.
- *Cite file:line / date · URL* makes evidence mandatory, so "trust me" can't pass.
- *What would change the answer?* for plans and decisions; the cheapest hedge against confident nonsense.
- Attach facts, not adjectives: row counts, dates, the failing test name, the exact error line.

## Reading a job folder

Every job writes `<domain>/.ai/jobs/<id>/` (hub jobs: `_system/router/jobs/<id>/`).

```
20260914T231501123456Z-write/
  contract.json        goal, domain, data_class, role, scope (read/write/effects/writer), authorization, limits, checks
  events.jsonl         created · dispatch · result · reviewer-fallback · escalate · escalation-refused · accepted/finished
  attempts/
    1/                 the work attempt
      request.json       purpose, vendor, model, tier, cwd, the exact prompt
      result.md          the artifact
      result.json        the adapter envelope: execution_status, exit_code, tokens, cost, elapsed, error
      stdout.txt         raw vendor output
      stderr.txt
      review-raw.txt     the reviewer's raw reply about this attempt (if a review ran)
      sandbox/           empty working dir for prompt-only vendors
    1-review-codex/    the reviewer's own call (same files: its exact prompt, its raw output)
    2/                 a repair or an escalation (purpose in request.json), then 2-review-…/
  verdict.json         per-check status + evidence, issues, reviewer, artifact sha256
  acceptance.json      the record the next agent reads first: acceptance_status, execution_status, checks, attempts
  result.md            the final artifact
```

Read in this order: `acceptance.json` (did it pass), `verdict.json` (why or why not), `attempts/*/request.json` (what was actually asked), `result.md` (what you got). `events.jsonl` tells the story in time order, with token counts and cost per attempt where the vendor reports them.

**Statuses**

| `acceptance_status` | Meaning |
|---|---|
| `pass` | Every declared check passed. The only state that unlocks dependent work. |
| `fail` | At least one check failed and repair/escalation did not fix it. Issues are in `verdict.json`. |
| `blocked` | Could not judge: execution failed or timed out, no eligible reviewer, artifact too large for review, reviewer returned no valid verdict, or an unknown builtin rule. Not a failure of the artifact; fix the cause and rerun. |

`ai accept <job-dir>` re-runs the deterministic checks on `result.md` after a manual fix.

## Council and consensus output

```
Orchestration: council claude/claude-sonnet-5 + codex/gpt-5.6-sol → judge claude-fable-5-1

## claude
<recommendation> (confidence high)
<reasoning>
Objections: none

## codex
<recommendation> (confidence medium)
<reasoning>
Objections: <objection>

## Judge
<one-paragraph decision> …

Council: JUDGED · <job dir>
```

```
Orchestration: consensus 5×tier-1 over claude+codex+grok+gemini

**Mode:** fail closed — 4/5 samples (80%), mean confidence 8.2/10

**Splits:**
- fail closed ×4 (claude, codex, gemini)
- warn only ×1 (grok)

**Outliers (unique ideas):**
- <an idea one sample raised that no other did>

Consensus: CONSENSUS · 5/5 valid · <job dir>
```

Say "consensus" when you mean a poll and "council" when you mean a decision. Don't run either on routine questions; ask for a `scout`.

## Publishing

Any write that crosses from a private domain into a public one is a publish. The flow:

1. Produce the content in its own domain (a `write` or `code` job, or by hand).
2. Stage it in `_publishing/` if it needs assembling from more than one domain.
3. From the hub root: `_system/gate/publish-gate.sh <target>` — if it blocks, stop and fix the content (or, with a human decision, add the exact line to `.publish-gate-allow`).
4. Copy into the public repo; commit and push. The hooks installed by `gate/install-hooks.sh` run the gate again on the staged index and on the push range.

`_system/gate/publish-check.sh --file X`, `--stdin`, `--diff` scan arbitrary input with the same markers before sharing anything anywhere.

## Handoffs and continuity

- End a substantial Claude Code session with `/wrap` (writes the handoff, runs pre-archive checks, then asks) or `/wrap archive`.
- From any shell: `_system/ops/session-handoff.sh --task "next step"` writes `_system/handoffs/<UTC>-handoff.md`.
- Rate-limited or switching vendors mid-task: `_system/ops/handoff-to-vendor.sh codex "next step"` (or `claude`) writes the handoff and prints the exact command that puts the other vendor's top model in the coordinator seat with the same rules.
- The next session starts with "Read the top entry of HANDOFF.md and continue", not with the old transcript.

## The cockpit

`<hub>/STATUS.md` re-renders after every job and on `make -C _system cockpit`. The attention list at the top is derived from the facts below it; a desktop notification fires only when that list changes. Read it before a work session.

## Environment variables

| Variable | Effect |
|---|---|
| `AI_GOVERNANCE` | Path to an alternate `governance.json` (tests and CI use this). |
| `AI_POLICY` | Path to an alternate `policy.json`. |
| `AI_NO_COCKPIT=1` | Don't refresh `STATUS.md` after jobs. |
| `COCKPIT_NOTIFY=0` | Render the cockpit without desktop notifications. |
| `PUBLISH_GATE_MARKERS` | Path to the markers file (overrides the repo's `.publish-gate-markers` and `gate/markers.txt`). |
| `GEMINI_API_KEY` | Read from the environment, else from a login shell. |
