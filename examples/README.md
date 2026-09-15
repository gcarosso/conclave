# Examples

Two complete job records, exactly as the router writes them (paths replaced with `<hub>`).

| Directory | What it shows |
|---|---|
| `job-scout-pass/` | A real tier-1 `scout` job run through Claude: one attempt, the `nonempty` builtin check, `PASS`. Read `acceptance.json`, then `events.jsonl` (tokens, cost, elapsed), then `attempts/1/request.json` for the exact prompt. |
| `job-write-review-repair-pass/` | A `write` job with cross-vendor review: Claude drafts, Codex reviews and **fails** the `goal-met` check with a located issue, Claude repairs with the reviewer's issues attached, Codex passes the repair. Four recorded calls (`1/` work, `1-review-codex/`, `2/` repair, `2-review-codex/`), `PASS`. Generated with the offline fake vendor, so the text is illustrative; the structure is real. |

Reading order for any job: `acceptance.json` → `verdict.json` → `events.jsonl` → `attempts/*/request.json` → `result.md`.
