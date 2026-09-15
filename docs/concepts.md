# Design rationale

Conclave gives a coordinating session a common way to dispatch LLM tasks and inspect their results. Its main design choice is to keep execution, evaluation, and acceptance as separate steps. For task decomposition, model roles, efficiency tradeoffs, and optional research tools, start with [multi-agent workflows](workflows.md).

## Define the evaluation target

A job contract records a goal, scope, authorization, resource limits, and checks. The kernel evaluates those checks and records the result. This gives a downstream reader a specific basis for deciding whether to use an output.

The CLI currently builds a default contract. It does not parse instructions such as “run pytest” into executable checks. Custom `builtin`, `command`, and `review` checks are supported by the Python kernel API; a contract-file CLI and resumable jobs are not implemented.

The default artifact is the model's returned text. A hash binds a verdict to that text. File edits, datasets, and test results need their own verification; hashing a response does not verify the files it describes.

## Separate model calls from acceptance

Adapters report whether the subprocess or API request succeeded. The verifier reports whether the declared checks passed. An execution failure blocks evaluation; a completed call can still fail a check.

This distinction is useful when a response is empty, omits required material, or lacks enough evidence to assess. It cannot compensate for a weak check: a nonempty response can be wrong.

## Review with another LLM

For `write` and `code`, a model from another provider receives the goal, review rules, and response in a new call. It returns a status and evidence for each rule, plus issues that can guide a repair. The writer's previous conversation is not forwarded.

Changing the reviewer can expose different errors, but model diversity does not establish statistical independence. Models can share failure modes, and reviewers can accept unsupported claims or respond to instructions embedded in the artifact. The package has no benchmark establishing an accuracy gain from review across providers.

A failed reviewer invocation can fall back to another eligible vendor. A valid failing verdict is retained. Missing, duplicate, or malformed review checks block acceptance.

## Bound retries and escalation

A normal job allows one repair and at most one escalation by default. Escalation requires a failing review with `capability_deficit: true`, an available model in the next tier, remaining call budget, and any required approval. The reviewer's flag is a judgment about the failure, not a measurement of model capability.

The call budget includes writer, reviewer, fallback, repair, and escalation invocations. A per-call timeout limits each adapter invocation. Token consumption, billing, child-process behavior, and total wall time are not controlled by a global cost or deadline budget.

## Route by policy

Roles specify a default vendor, tier, permissions, and review setting. Vendor ladders map tiers to model IDs. This lets an operator change models without changing every task command.

Choose roles around the required capability: reasoning and planning, code execution, multimodal input, or current-source retrieval. Model selection alone does not supply a missing tool or input format. For example, Conclave's Gemini adapter accepts text; video understanding needs a separate integration. The [workflow guide](workflows.md#choose-models-by-role) maps these requirements to model roles and current adapter support.

The router checks configured eligibility and availability; it does not optimize cost or select a model from measured capability. `ai auto` adds a model-based classification step. Explicit role selection remains useful when the task or execution constraints are already clear.

## Compare recommendations

`council` requests two recommendations separately, then optionally asks a judge to resolve disagreement. The member calls run sequentially and do not receive each other's answers. Agreement uses case-insensitive text equality plus an empty objections list, so equivalent wording can still trigger a judge.

`consensus` runs samples concurrently across eligible vendors and prompt framings. It groups recommendations and reports the modal share, splits, self-reported confidence, and submitted ideas. Shared training data and changed prompts make this a structured comparison rather than an independent sampling experiment. Modal share and confidence are not probabilities that an answer is correct. “Outliers” collects distinct submitted idea strings; it does not measure statistical rarity.

## Keep state inspectable

Contracts, attempts, responses, and verdicts remain on disk. Handoffs can point to those records, making it possible for another session to continue the work after reviewing the evidence. Continuing is a manual workflow; the package has no scheduler, dependency graph, or automatic resume command.

For shared edits, an advisory OS lock excludes another router job with the same declared write set in that domain. It does not lock an editor, a raw vendor CLI, or a partially overlapping write set.

## Make boundaries explicit

Governance generates instructions and Claude tool-deny settings. Routing restricts which vendor may receive a job's payload. These controls operate at different levels; generated instructions and empty working directories do not provide process isolation.

The publication gate searches configured regex patterns in raw file bytes and Git blobs. It blocks on matches and scan errors, but does not decode archives or identify every secret. The registry likewise reports specific observations: a CLI version probe does not test authentication or validate every model in a policy file.

## Related work

The package combines explicit task specifications, separate evaluation, bounded retries, ensemble comparison, advisory locks, and file-based coordination. Its council interface was informed by [Andrej Karpathy's LLM Council](https://github.com/karpathy/llm-council). See the [workflow guide](workflows.md#delegation-review-and-council) for the distinction between that project's peer ranking and Conclave's two-member council.
