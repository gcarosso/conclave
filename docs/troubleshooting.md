# Troubleshooting

| Symptom | First move |
|---|---|
| `ai: no governance file at …` | `ai init` (or `install.sh --init`). To point at another file: `AI_GOVERNANCE=/path/governance.json`. |
| `ai: cwd is outside the hub; pass --domain` | You are not under the hub. `cd <hub>/<domain>` or add `--domain <name>`. |
| `ai: cwd is under the hub but not inside a known domain: X` | The folder is not in `governance.json` `domains`. Add it and `make generate`, or run from a known domain. |
| `ai: blocked: data_class=private in work admits only claude/codex; grok refused` | The data class does not admit that vendor. Either the task is fine to declassify (`--data-class sanitized`, recorded in the contract) or it is a Claude/Codex task. `--dry-run` shows the route without running. |
| `ai: gated: claude-fable-5-1 requires approval (pass --approve-top-model)` | The model is gated and the run is non-interactive. Add the flag in scripts, or run in a terminal and answer the prompt. |
| `ai: unknown model id …` / `model … is marked unavailable` | `policy.json` `models` is the allowlist. Add or enable the id and re-run `ai smoke`. |
| `ai: ladder codex tier 2 -> gpt-x is not an available model` | The ladder points at an id that is missing or `available: false`. Fix the ladder. |
| `ai: write set locked by running job …` | Another job owns that write set. Wait, or if it is dead, delete `<domain>/.ai/jobs/locks/<hash>.lock` (finished jobs' locks are reclaimed automatically). |
| `Acceptance: BLOCKED` | Not a failed artifact. `verdict.json` evidence says why: `execution failed/timeout` (vendor CLI, auth, network), `no eligible reviewer` (data class excludes every other vendor → `--no-review` or widen the class), `artifact … exceeds review limit; split the job`, `reviewer output invalid` (rerun; tier-1 reviewers occasionally drop a key), `unknown builtin rule`. |
| `Acceptance: FAIL` after a repair | Read `verdict.json` issues; fix by hand and `ai accept <job dir>`, or rerun with a sharper "done means". If an issue has `capability_deficit: true`, rerun with `--approve-top-model` to allow the escalation. |
| `ai smoke` → `FAIL: cli-not-found` | The vendor CLI is not on PATH. Install it or ignore the vendor (it is never routed to unless a role or flag asks). |
| `ai smoke` → `FAIL: … not logged in` | `claude login` · `codex login` · `grok login`. |
| `ai smoke` → gemini `GEMINI_API_KEY not set` | Export it in your shell profile; the adapter reads the environment, then a login shell. `pip install google-genai` for the SDK. |
| `Council: BLOCKED` | A member returned no valid JSON. Rerun; if it persists, the question may be too open to answer in one sentence — tighten it. |
| `Council: DISAGREE` | The judge was refused (gated, non-interactive) or its vendor is not eligible for the data class. Rerun with `--approve-top-model`, or read both answers and decide. |
| `Consensus: BLOCKED` | Fewer than half the samples were valid. Check `result.md` in the job dir for which vendor failed; `ai smoke`. |
| `Consensus: SPLIT` | Working as intended: the mode is under 60%. The splits *are* the answer. |
| `PUBLISH GATE: BLOCKED — no markers file` | Copy `gate/markers.example.txt` to `gate/markers.txt` and edit. The gate fails closed on purpose. |
| `PUBLISH GATE: BLOCKED — private markers` | Fix the content. If a hit is intentional, add the exact printed line to `<repo>/.publish-gate-allow` after a human decision. |
| `PUBLISH GATE: BLOCKED — scan error` | A file was unreadable, `grep` errored, or a git command failed. Fix the cause; the gate never reports clean on an error. |
| `PUBLISH GATE: BLOCKED — no @{push} or @{upstream}` | `--diff` needs a range. Pass one explicitly or set an upstream; the installed pre-push hook computes ranges itself. |
| `make drift-check` reports DRIFT | Someone hand-edited a generated file. `make generate` overwrites it from `governance.json` (put the change there instead). |
| Cockpit says `registry not generated` | `make registry` (optionally after `cp registry/config.example.json registry/config.json`). |
| Cockpit notifications are noisy | `COCKPIT_NOTIFY=0` in the environment of whatever runs it; notifications only fire when the attention list changes. |
| A job's `attempts/1/stderr.txt` shows a vendor flag error | The vendor CLI changed its flags. `adapters.py` is the only file that knows them; update the one function and `ai smoke`. |
| Tests fail after editing `policy.json` | The suite's expectations follow the shipped ladders (`claude-haiku…` at tier 1, `gpt-5.6-sol` for `code`). Update the assertions in `router/tests.py` when you change defaults. |

## Where the evidence is

- The job folder, always: `acceptance.json` → `verdict.json` → `events.jsonl` → `attempts/*/`.
- `ai jobs` for the last fifteen verdicts; `<hub>/STATUS.md` for everything at a glance.
- `registry/REGISTRY.md` for what was reachable and when.
- `_system/handoffs/` for what the last session decided.
