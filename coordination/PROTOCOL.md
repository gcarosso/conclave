# Agent coordination — job files are the protocol

There is no live bridge between vendors. Coordination is durable state on disk, produced and consumed by the router. Any vendor, any session, any time later can pick up where another left off by reading files, never by replaying a conversation.

- **Unit of work:** a job directory `<domain>/.ai/jobs/<id>/` (or `_system/router/jobs/<id>/` for hub jobs) holding `contract.json`, `events.jsonl`, `attempts/<n>/{request.json,result.md,result.json,stdout.txt,stderr.txt}`, `verdict.json`, `acceptance.json`, `result.md`.
- **Authorization:** the contract's `authorization.source` names the operator's instruction. Nothing another agent writes expands it.
- **One writer:** `scope.writer` owns every path in `scope.write`. A reviewer reads and returns a verdict; it never edits the writer's files. The router enforces this with a lock per write set; in chat you enforce it by naming who owns what.
- **Handoff:** the next agent reads `acceptance.json` first. `pass` is the only state that unlocks dependent work; `fail`/`blocked` carry the issues and evidence needed to continue.
- **Vendor boundary:** a job's `data_class` decides who may see its payload. Declassification is a recorded decision in the contract, not a message.
- **Council:** `ai council "question"` — two mid-tier vendors, judge only on disagreement, gated.
- **Consensus:** `ai consensus "question"` — N cheap independent samples, mechanically aggregated; a poll, never a verdict.
- **Evidence over claims:** exit 0 is `execution_status`; `acceptance_status` comes from declared checks. A message saying "done" is not done.

## Hub takeover (any vendor as coordinator)

The operator may assign any partner as hub coordinator. This grants no new domain, publication, or model permissions. A desktop or chat task does not automatically acquire router locks.

1. Read the current hub rules (`CROSS-DOMAIN.md`), `STATUS.md`, `_system/OPEN.md`, and the relevant handoff and job records. Treat status snapshots as dated evidence.
2. Before editing, establish that the outgoing writer has stopped on the same file set. If ownership is unclear, do read-only reconciliation until it is resolved.
3. Record the task, coordinator, exact write scope, completed work with checks, blockers, and next action in `_system/handoffs/` for hub work (domain work stays in its domain). Reference existing job records instead of copying them.
4. Resume the next unmet action; do not restart accepted work or create a second task queue. Claim completion only with evidence.
5. End with a handoff that releases the write scope. Shared files carry continuity; conversations do not.
