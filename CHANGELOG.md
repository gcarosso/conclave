# Changelog

## Unreleased

- Added `scripts/e2e.sh` (`make e2e`): a temporary hub driven through the real `ai` CLI with fake `claude` and `codex` executables, covering install, generation, a data-class refusal, a reviewed write job with a rejected first draft and repair, handoffs, cockpit, gate hooks, and the registry probe. `--live` runs one real scout job. CI runs it in place of the inline bootstrap step.
- Added `scripts/check-links.py` (`make check-links`, part of `make test`): relative Markdown links and heading anchors must resolve.

- Rewrote documentation around routing, response evaluation, job records, and adapter limits. Removed unmeasured quality and cost claims.
- Made `auto --dry-run` skip classification, and made explicit model selection respect `--max-tier`.
- Applied catalog and approval checks before recorded adapter dispatch, including reviewers and council members; preserved council judge approval and declassification records.
- Used read-only reviewer settings, forwarded review schemas, and recorded the reviewer that returned the verdict after fallback.
- Counted review and fallback calls in the standard-job budget. Wrote the current response before command checks; rejected duplicate review checks and invalid builtin rules.
- Replaced reclaimable lock files with advisory OS locks held for the job lifetime. Read-only jobs no longer contend on a shared `result.md` lock.
- Corrected generated Claude permission paths to recursive absolute-path syntax.
- Scanned staged and historical Git blobs directly, including binaries above the previous size cutoff. Exact-line finding format is now consistent across modes; regenerate old `+diff-line` exceptions.
- Required explicit approval before preparing a gated vendor handoff; preserved ShellCheck failure status and reported unknown Codex cost as null.

## 0.1.0 — initial package

- CLI for routed tasks, auto-classification, council, consensus, and job inspection.
- Contracts, response checks, cross-vendor review, bounded repair, and escalation.
- Governance generator, marker scanner, registry, status page, and manual handoffs.
- Offline tests and a CI workflow configured for Linux and macOS.
