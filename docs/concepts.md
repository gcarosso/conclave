# Concepts: the reasoning methodology

Conclave is a small set of mechanisms, each answering one failure mode of agentic work. This page explains each mechanism, the reasoning method it implements, why that method works, and what it confers. Read it once; the rest of the docs assume it.

## 1. Contract-first execution

**The failure.** Agents hallucinate and over-engineer when success is undefined, and quietly cut corners when failure is undefined. "Improve this" gets a fluent guess.

**The mechanism.** Every job starts as a contract (`contract.json`, validated against `router/contract.schema.json`): the goal, the domain, the data class, the writer, what may be read and written, what side effects are allowed, who authorized it, the limits, and the **checks** that define done. Checks are of three kinds:

| kind | what it is | who decides |
|---|---|---|
| `builtin` | `nonempty`, `contains:`, `not_contains:`, `regex:`, `file_exists:`, `min_words:` | the kernel, deterministically |
| `command` | any shell command run in the job directory; exit 0 passes | the kernel, deterministically |
| `review` | a rule in prose, judged by a fresh-context reviewer | another vendor, with evidence |

**Why it works.** The FAILURE clause is the innovation (this is the *Prompt Contracts* pattern made executable). A goal with a checkable "done means" gives the reviewer something to reject and the kernel something to compute. A prompt that cannot state its own acceptance check is not ready to run.

**What it confers.** Reproducibility (the contract is on disk), auditability (authorization is structured data), and the separation that makes everything else possible: `execution_status` (the process ran) is never confused with `acceptance_status` (the checks passed).

## 2. Verdicts, not exit codes

**The failure.** Most tooling reports success when the subprocess exits 0. A refusal, a partial result, or an empty file all exit 0.

**The mechanism.** `verify.py` evaluates the contract's checks against the artifact and writes a verdict (`verdict.json`, validated against `router/verdict.schema.json`): per-check status with evidence, a list of issues with severity and a proposed fix, and the artifact's SHA-256 so the verdict is bound to exactly what was judged. The decision rule is strict: any `blocked` check → `blocked`; any `fail` → `fail`; otherwise `pass`. An execution failure blocks every check. The **worker never awards PASS**; the kernel does, from the verdict.

**Why it works.** A verdict is falsifiable: it names the check, the status and the evidence. "Trust me" cannot pass.

**What it confers.** Exit 0 from `ai` means the declared checks passed. The last line of every job is `Acceptance: PASS|FAIL|BLOCKED · <job dir>`; `acceptance.json` in the job folder is the durable record the next agent reads first.

## 3. Fresh-context cross-vendor review

**The failure.** A model reviewing its own output shares its blind spots and its sunk cost. Same-model review mostly agrees with itself.

**The mechanism.** When a contract has a `review` check (the default for `write` and `code`), the kernel picks a reviewer from a *different* vendor (`reviewer_for` in `policy.json`: Claude's work is reviewed by Codex and vice versa), subject to the same data-class eligibility as the writer. The reviewer sees only the goal, the checks and the artifact, never the writer's reasoning or files, and must return structured JSON: one status per check with a quote or line as evidence, plus issues. Free-text verdicts are rejected; a reviewer that fails to execute is replaced by the next eligible vendor, but a reviewer's *judgment* is never overridden by fallback. Artifacts over the review size limit block instead of being silently truncated.

**Why it works.** Fresh eyes catch what the implementer misses, for the same reason human code review works. Using a different model family also decorrelates errors: two models trained differently are less likely to share the same confident mistake.

**What it confers.** A 2–3× quality lift on written and coded artifacts in practice, and a machine-readable list of what is wrong, which feeds the next mechanism.

## 4. Bounded repair and gated escalation

**The failure.** Retry loops that run until the budget is gone, or that jump to the most expensive model at the first sign of trouble.

**The mechanism.** On `fail`, the kernel sends the writer its own artifact plus the reviewer's issues and asks for a complete corrected version, once (`limits.repairs`, default 1). If that still fails **and** the reviewer marked an issue `capability_deficit: true` (the failure needs a stronger model, not a correction), the kernel escalates one tier (`limits.escalations`, default 1), passing through the top-model gate if the next tier is gated. Total calls are capped (`limits.calls`). Every step is an event in `events.jsonl`.

**Why it works.** Refinement with explicit stop conditions converges or stops; escalation on the reviewer's evidence rather than on mere failure keeps expensive models for the cases that need them.

**What it confers.** Predictable cost per job, no runaway loops, and a trail that shows exactly why a top model was or was not used.

## 5. Capability-fit routing: roles, tiers, ladders

**The failure.** Vendor loyalty and leaderboard prestige: sending everything to the biggest model because it is there.

**The mechanism.** A **role** (`scout`, `plan`, `code`, `write`, `review`, `live`, `longdoc`, …) carries a default vendor, a default **tier** (1 cheap, 2 workhorse, 3 top), a turn budget, a sandbox mode and whether review is on by default. Each vendor has a **ladder** mapping tiers to concrete model ids. The router resolves role + flags into one (vendor, model, tier), refusing unknown or unavailable ids: `policy.models` is an allowlist, and `ai smoke` re-verifies it.

**Why it works.** Most work is tier-2 work; most lookups are tier-1 work. Naming the role instead of the model lets the policy, not the moment, decide.

**What it confers.** The smallest adequate model by default, one place to update when a model id changes, and vendor portability: swap a ladder and every role follows.

## 6. Scout-then-specialist triage (`ai auto`)

**The failure.** Users who don't know the roles either over-spend (everything at tier 3) or under-spend (a code fix at tier 1).

**The mechanism.** `ai auto "task"` makes one tier-1 call with a classification-only prompt and a JSON schema, gets `{role, tier, review}`, and then runs the task through the normal path with those settings. Flags you pass explicitly win over the triage.

**Why it works.** Classification is cheap and models are good at it; the expensive call is then right-sized.

**What it confers.** A single entry point that still produces a proper contract and verdict.

## 7. Council: independent advisors, judge on disagreement

**The failure.** One model, one answer, no way to tell whether it is great or mediocre; or a "debate" where the second model anchors on the first.

**The mechanism.** `ai council "question"` asks two mid-tier vendors the same question **independently** (neither sees the other's answer), each returning a recommendation, a confidence, reasoning and blocking objections as JSON. If the recommendations match and neither raised an objection, the council reports `agree` and stops. Otherwise a tier-3 judge, behind the approval gate, is given both answers and asked to resolve the disputed propositions and say what to do; the council reports `judged`, or `disagree` if the judge was refused.

**Why it works.** Independence removes anchoring; disagreement between two good models is a stronger signal than either one's confidence; adjudication is spent only where there is something to adjudicate.

**What it confers.** Decision support that is cheap in the common case and strong in the hard case, with the whole exchange on disk.

## 8. Stochastic consensus: a poll, never a verdict

**The failure.** A single run of a strategic question reflects one sample of a stochastic process, plus whatever framing you happened to use.

**The mechanism.** `ai consensus "question" --n 5 --options "A;B;C"` runs N tier-1 samples in parallel, cycling ten **framings** (conservative analyst, first-principles, end-user view, second-order effects, …) and rotating over every eligible vendor. Each returns a pick, a 1–10 confidence, reasons and one "idea most would miss". Aggregation is mechanical: the **mode** (with share and mean confidence), the **splits**, and the **outliers**. Fewer than half valid samples blocks; a mode under 60% is `split`.

**Why it works.** Polling ten experts beats asking one. The mode filters individual hallucinations; the splits reveal genuine judgment calls; the outliers surface ideas a single run would never show. Vendor rotation decorrelates biases the way cross-vendor review does.

**What it confers.** Breadth for the price of cheap calls, and honest output: it is labelled a poll because that is what it is.

## 9. Least context: data classes and sandboxing

**The failure.** "Allowed in the domain" is read as "safe to receive every file in the domain", and prompt-only APIs are handed working directories they never needed.

**The mechanism.** Every domain has a default **data class** (`private`, `sanitized`, `public`); every class lists the vendors that may see it; a domain may further restrict its vendors. Eligibility is the intersection. Raising a payload's class for one task (`--data-class sanitized`) writes a **declassification record** into the contract: from, to, by whom, when, and the stated reason. Prompt-only vendors (Grok, Gemini) always run from an empty sandbox directory under the attempt: the prompt is their whole payload.

**Why it works.** Need-to-know applied to models. The decision to widen exposure is deliberate and recorded, not implied.

**What it confers.** You can open private domains to more vendors later without touching the mechanism, and every widening is auditable.

## 10. The top-model gate

**The failure.** Expensive or high-capability models get used by default, or by a script nobody reviewed.

**The mechanism.** Models marked `requires_approval` in `policy.json` (and listed in `governance.top_model_gate`) need the operator's approval per use: `--approve-top-model` in scripts, or an interactive y/N. The approval record (model, approver, via, timestamp) is written into `contract.authorization.top_model_approval`. Non-interactive runs without the flag are refused, including escalations and council judges.

**Why it works.** The expensive model is not the trustworthy one; the check is. Gating puts the human where the cost and the stakes are.

**What it confers.** Cost control and an audit trail from the same field.

## 11. One writer per write set

**The failure.** Two agents editing the same files produce a merge, not a result.

**The mechanism.** The contract's `scope.write` is hashed into a lock file created with `O_EXCL`. A second job on the same write set is refused while the first is running; locks of finished jobs are reclaimed automatically. Councils and consensus runs release their lock immediately: they advise, they own nothing.

**Why it works.** Mutual exclusion is the oldest coordination primitive because it is the one that actually works.

**What it confers.** Safe parallelism across vendors and sessions without a coordinator process.

## 12. Generated governance

**The failure.** The same rule written five ways in `CLAUDE.md`, `AGENTS.md`, a README, a policy file and a handoff; each vendor reads a different version.

**The mechanism.** `shared/governance.json` is canonical. `router/generate.py` renders `CROSS-DOMAIN.md`, the hub-root and per-domain `CLAUDE.md` (Claude Code) and `AGENTS.md` (Codex), and per-domain `.claude/settings.json` deny rules that block every sibling domain. Generated files carry a header saying so. `--check` reports drift; the cockpit runs it after every job.

**Why it works.** One source, many surfaces; hand edits become visible instead of silently diverging.

**What it confers.** Materially equivalent governance for every vendor, and technical isolation for the one vendor (Claude Code) whose CLI supports deny rules.

## 13. Fail-closed publication

**The failure.** A scanner that prints "clean" when `grep` errored, skips dotfiles, or ignores binaries; hooks that run at push time only, after private content is already in history.

**The mechanism.** `gate/publish-gate.sh` scans a whole tree (tracked and untracked, dotfiles included), the staged index (pre-commit), or every commit in a push range (pre-push), for the extended-regex markers you list. Binaries are checked with `strings`. Any scan error, git error, unresolvable range, or missing markers file **blocks**. Exceptions are exact lines in an allowlist file, reviewed by a human. Twenty-two fixtures pin the behavior.

**Why it works.** A control that can fail open is not a control. The gate's only two outcomes are "clean, and here is what I scanned" and "blocked, and here is why".

**What it confers.** The invariant "no private marker is ever committed to a public repo", enforced at both commit and push.

## 14. Observed state over declared state

**The failure.** A static inventory that describes expired connections, renamed models, and unloaded jobs as current.

**The mechanism.** `registry/generate.py` probes each vendor CLI, lists MCP servers and skills from their config files, checks scheduled jobs, and copies the model catalog with its gate flags. Every probe records its own `observed_at` and `status`; a failed probe is recorded as failed, never omitted. `registry.json` is the source; `REGISTRY.md` is a view. The audit script snapshots, regenerates, diffs and returns the issue count as its exit code.

**Why it works.** Routing and troubleshooting decisions made on stale capability data are wrong in ways that are hard to see.

**What it confers.** A dated, honest picture of what is actually reachable.

## 15. Derived attention

**The failure.** A dashboard you have to read to know whether anything is wrong.

**The mechanism.** `ops/cockpit.sh` renders `STATUS.md` from live facts (jobs, vendors, router health, recent verdicts, public repos, open items) and then derives an **attention list** from those facts: unloaded jobs, failed probes, failing tests, drift, failed fixtures, failed or blocked jobs, unpushed commits. The list is at the top. A desktop notification fires only when the list changes.

**Why it works.** Conditions computed from facts are checkable; a notification on delta is one you will read.

**What it confers.** One glance says whether anything needs you.

## 16. Coordination through artifacts

**The failure.** Continuity that lives in a chat transcript: the next session, or the next vendor, has to reconstruct it, dead ends included.

**The mechanism.** The job folder is the protocol (`coordination/PROTOCOL.md`): contract, attempts, verdict, acceptance. The next agent reads `acceptance.json` first; only `pass` unlocks dependent work. Handoffs (`ops/session-handoff.sh`, `ops/handoff-to-vendor.sh`, the `/wrap` skill) record goal, changed paths, evidence, decisions, open items and the next command, on disk, in the domain the work belongs to.

**Why it works.** Files outlive contexts and cross vendors; conversations do neither.

**What it confers.** Any vendor can take over any job, and the evidence that it was done survives the session that did it.

## Where these come from

Several of these mechanisms are executable forms of patterns that circulate as prompt-level techniques: prompt contracts with explicit failure clauses, subagent verification loops with a fresh reviewer, stochastic multi-agent consensus with framing variation, and Andrej Karpathy's LLM-council idea of independent answers plus adjudication. Conclave's contribution is to move them out of the prompt and into a kernel with schemas, limits, locks, an audit trail and tests, so that the behavior is enforced rather than requested.
