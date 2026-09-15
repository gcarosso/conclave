# Example job records

These are preserved records from the initial package, with paths replaced by `<hub>`. They illustrate the file format; they are not output from the current regression suite.

| Directory | Provenance and behavior |
|---|---|
| `job-scout-pass/` | Captured Claude tier-1 scout call. One attempt passes the `nonempty` check. It demonstrates a live response record, not factual validation of that response. |
| `job-write-review-repair-pass/` | Offline fixture using a fake vendor. A simulated Claude draft fails simulated Codex review, receives a repair, and passes a second review. Four call records show the sequence; no live cross-vendor execution is claimed. |

Read `acceptance.json`, `verdict.json`, `events.jsonl`, then the attempt requests and responses. Writer and reviewer calls occupy separate directories. Model names and usage in historical records do not establish current account availability or billing.
