---
name: wrap
description: "End a session safely: write the handoff, run pre-archive checks, and archive only when told. Use when the operator types /wrap, /wrap archive, 'wrap', 'wrap it up', or 'handoff and archive'."
---

# Session handoff and archive

`/wrap` writes the handoff and runs the checks, then asks. `/wrap archive` also archives this session if every check passes; typing it counts as the operator's explicit consent.

## 1. Locate
- cwd is the hub root → hub handoff.
- cwd is inside `<hub>/<domain>` → domain handoff.
- Anywhere else → print the HANDOFF block only and ask which domain it belongs to. Write nothing.

## 2. Inventory this session (verify, don't recall)
- Files created or changed: from the conversation, confirmed with `git status --short` in each touched repo and `ls -lt` on touched dirs.
- Router jobs: entries in `_system/router/jobs/index.jsonl` created during this session, with their `acceptance_status`.
- Still running: background shell tasks, workflows, subagents, `ai` jobs holding a writer lock.
- Transcript: the newest session transcript file, if the client keeps one (its path goes in the handoff so the full context stays findable).

## 3. Write the handoff (≤40 lines)
Sections: **Goal & authorization** · **What changed** (paths) · **Evidence** (tests, verdicts, job dirs, hashes) · **Decisions & why** · **Open / blocked** · **Next action** (the first command to run) · **Transcript** (session id + path).
- Hub root → `_system/handoffs/<UTC-timestamp>-<slug>.md`; add each deferred item to `_system/OPEN.md` (one line each, no duplicates).
- Domain → prepend a dated entry to `<domain>/HANDOFF.md`; older entries stay below.

## 4. Memory
Update persistent memory only when the operator explicitly requests it. Keep private document contents and sensitive personal details out of memory; record task evidence in the workspace handoff.

## 5. Pre-archive checks
| Check | Pass when |
|---|---|
| Uncommitted work | Every touched repo is clean, or its changes are listed in the handoff as intentional. Commit only within the operator's authorization. |
| Running work | No background task, workflow, or locked `ai` job belongs to this session. |
| Governance | If `governance.json` or generated files were touched: `make -C _system/router drift-check` is clean. |
| Tests | If router code was touched: `make -C _system/router test` is OK. |
| Cockpit | In the hub: `make -C _system/ops cockpit` ran; its Attention list is in the handoff. |
| Handoff | The file exists and names a next action. |

## 6. Report and archive
Report the handoff path, completed checks, and any unresolved item.
- `/wrap` → end with: "Ready to archive — `/wrap archive` or say archive."
- `/wrap archive` → if every check is ✓, archive this session; if any is ⚠, don't archive — list what needs the operator.
Archiving is reversible; the transcript stays on disk.
