# Coordination protocol

Keep the goal, working plan, and final integration with one coordinating session. Delegate bounded tasks through `ai`, then use the returned evidence to decide what comes next. Job records and handoffs preserve this state when work moves to another session.

The coordinator supplies task decomposition and scheduling. Conclave does not relay messages between desktop chats or automatically resume a job. See [multi-agent workflows](../docs/workflows.md) for model roles and optional research tools.

## Ownership and evidence

- A standard job directory contains its contract, attempts, response, verdict, and acceptance record. Start with `acceptance.json`, then inspect the checks and evidence.
- Treat `pass` as permission to use an output only when the declared checks are sufficient for the next task. Council and consensus have separate result formats.
- The authorization source defines the task. A message from another agent does not expand it.
- Name one writer for each shared file set. Router jobs with identical declared write sets share an advisory lock; desktop sessions and partially overlapping paths require explicit coordination.
- Reviewers return findings. They do not own the writer's file changes.
- A data-class override records a classification decision. It does not sanitize content.

## Handoff

1. Read current instructions, `STATUS.md`, the relevant handoff, and job records. Note when observations were made.
2. Confirm the outgoing writer has stopped before editing the same files.
3. Record the task, writer, write scope, completed changes, verification, blockers, and next action.
4. Continue from the next unmet action. Preserve completed work and cite its existing evidence.
5. Release ownership in the closing handoff.

Hub handoffs belong in `_system/handoffs/`; domain handoffs stay in the domain. `ops/session-handoff.sh` writes a workspace snapshot that can be supplemented with task-specific evidence. `/wrap` adds session inventory and archive checks. A handoff names the next action; executing it starts new work under the current authorization.
