# Architecture

## Components and state

```text
router/ai → kernel.py → adapters.py → vendor CLI or SDK
                └──→ verify.py → check results and acceptance
```

The kernel owns routing and job state. Adapters normalize vendor output. The verifier runs deterministic checks and accepts a reviewer callable supplied by the kernel. Tests replace `adapters.run` with a fake; vendor behavior is outside those tests.

The checkout normally lives at `<hub>/_system/`, alongside domain directories. Governance generates instructions for each domain. Standard jobs write into that domain's `.ai/jobs/`; the router maintains a shared JSONL index.

## Standard job lifecycle

1. Resolve domain, data class, role, vendor, tier, and model. Check eligibility and catalog availability.
2. Obtain any required model approval and build the contract.
3. Acquire the advisory writer lock, then create the job record.
4. Run the adapter and save its request, returned text, raw output, and execution status.
5. Write the current response to `result.md`; evaluate builtins, commands, and any review rules.
6. On failure, attempt the permitted repair. Escalate at most once when a review identifies a capability deficit and policy, approval, tier cap, and call budget permit it.
7. Write the verdict and acceptance record, release the lock, and request a status refresh.

Execution failures block evaluation. A blocked check takes precedence over a failed check; all checks must pass for acceptance. Reviews over the character limit block rather than receiving a truncated artifact.

## Contracts and checks

The CLI constructs a contract containing:

- Task metadata: `id`, `goal`, `role`, `domain`, and `data_class`.
- Scope: declared read paths, write paths, effects, and writer.
- Authorization: source, declassification, and model approval.
- Limits: adapter calls, per-call timeout, repairs, escalation, and review length.
- Checks: an ID, kind, and rule for each evaluation.

The included validator supports types, enums, required fields, properties, array items, and `additionalProperties`. It is a subset of JSON Schema, not a general schema implementation.

| Kind | Evaluation |
|---|---|
| `builtin` | `nonempty`, `contains:`, `not_contains:`, `regex:`, `file_exists:`, or `min_words:` |
| `command` | Shell command in the job directory; exit 0 passes, timeout blocks |
| `review` | Another vendor evaluates a prose rule against the goal and response |

Custom checks are available through `kernel.build_contract(..., checks=[...])`. The CLI adds only `nonempty` and, when enabled, `goal-met` review. Prompt text does not become a shell command. Command checks are trusted local code and are not sandboxed by Conclave.

## Review and provenance

A review receives the goal, review rules, and current response. It does not receive the writer's prior conversation. The router requests structured output where supported and validates the parsed result. Every requested check must appear once. Fallback occurs on invocation failure, never to replace a valid failing judgment.

If the initial work call fails to execute, the router tries other eligible vendors at the same tier within the job's call budget. It skips unavailable and approval-gated models; writing roles can fall back only to Claude or Codex. A failed quality check follows the repair path instead. Execution fallback does not apply to repair or escalation calls.

Claude writing roles receive `--permission-mode acceptEdits` so headless runs can edit files. Existing deny rules still apply; reviewer calls never receive that permission mode.

Reviewer requests use the review role's read-only settings, a separate working directory, and no requested network access. Claude review disables built-in tools, MCP configuration discovery, and slash commands. Codex uses its read-only sandbox. Host configuration and vendor behavior still affect available context; this is not a hermetic evaluation environment.

Each writer and reviewer call has its own attempt directory. The verdict records the reviewer that actually returned it, including after fallback. `artifact_sha256` covers returned text only. The standard review does not evaluate a captured repository diff, rerun the worker's claimed tests, or hash modified files.

`acceptance.json` summarizes writer attempts; reviewer details remain in `events.jsonl` and `attempts/`. Council and consensus have separate result formats and no standard acceptance verdict. Auto-classification precedes the normal job and is not stored as a complete attempt record.

## Enforcement boundary

| Control | Implementation and limit |
|---|---|
| Vendor eligibility | Intersection of configured domain and data-class vendor sets; checked before dispatch |
| Model selection | Catalog membership, availability flag, vendor match, and required approval; availability is configuration, not discovery |
| Resource limits | Standard-job call counter includes review and fallback; timeout applies per adapter call. No global token, dollar, or wall-time budget |
| Writer exclusion | Advisory `flock` per identical write set and domain; closes on release or process exit. It does not detect arbitrary path overlaps or lock other applications |
| Read-only roles | Codex receives `read-only`; other adapter controls differ. A role label alone is not a filesystem permission |
| Claude file access | Generated recursive, absolute-path deny rules for sibling domains' file tools; shell commands and other tools need separate controls |
| Grok and Gemini context | Empty working directory. Gemini sends prompt text to the SDK; the local Grok CLI still runs with host credentials and tool behavior |
| Data classification | Restricts vendor choice and records widening of classification. It does not redact content |
| Publication | Operator workflow plus optional Git hooks; the router does not intercept every filesystem write or automatically run the gate |
| Job records | Mutable local files. Checks and hashes aid inspection but do not make records tamper-proof |

Claude rules use the documented `Read(//absolute/path/**)` syntax. File-tool deny rules do not create an OS sandbox. [Claude permission reference](https://code.claude.com/docs/en/permissions).

## Adapter interfaces

| Adapter | Invocation |
|---|---|
| Claude | `claude -p`, model, JSON output, turn limit, and optional settings/schema |
| Codex | `codex exec`, model, sandbox, working directory, ephemeral session, JSON events, and last-response file |
| Grok | `grok --single`, model, working directory, turn limit, and JSON output; web search enabled for `live` |
| Gemini | `google.genai.Client.models.generate_content` in a Python subprocess |

Envelopes record `execution_status`, `exit_code`, text, session ID, timing, usage, cost when available, errors, and raw output. Missing cost is `null`. Turn limits are passed to Claude and Grok; the Codex and Gemini adapters do not implement them.

## Publication gate

| Mode | Scope |
|---|---|
| Tree | Git tracked and untracked nonignored files, including dotfiles; ordinary files under non-Git trees |
| `--staged` | Complete index blobs for added or modified files, independent of the working tree |
| `--diff` | Changed file blobs in every commit of the selected range, including root and merge commits |

The scanner applies case-insensitive extended regexes to raw bytes, with no size cutoff. It blocks on matches, missing marker configuration, unreadable inputs, invalid patterns, and Git errors. It does not decode compressed or encrypted content, recurse into submodules, or replace a dedicated secret scanner. Gitlinks it cannot read as blobs block the scan. Non-Git traversal does not follow directory symlinks.

Exact-line exceptions use `path:line:text` or the printed binary finding. Marker and allowlist files are excluded from findings and need separate review. Hooks can be bypassed or absent. Scan the full destination tree before an initial release, then use index and history scans for subsequent publication.

## Extension points

Add vendors in `adapters.py`, roles and models in `policy.json`, checks in `verify.py`, and registry probes in `registry/generate.py` or its configuration. Update tests for changes to dispatch, acceptance, permissions, or scan coverage. Keep generated instructions aligned with governance using `make drift-check`.
