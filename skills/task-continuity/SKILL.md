---
name: task-continuity
description: Preserve and restore the essential state of a long-running Codex task. Use when the user asks to checkpoint, hand off, pause, switch accounts, or resume work, and when the runtime reports that the five-hour usage window has 10% or less remaining or the model context has 15% or less remaining. Do not activate for ordinary short-task summaries.
---

# Task Continuity

Create a durable handoff that lets a new Codex session continue without repeating
completed work or losing user constraints. A checkpoint is semantic state, not a
transcript dump.

## Choose a mode

- **checkpoint**: Save the current task. Use this for an explicit request or an
  automatic threshold signal. Read [checkpoint-schema.md](references/checkpoint-schema.md).
- **resume**: Restore the latest checkpoint and continue safely. Read
  [resume-protocol.md](references/resume-protocol.md).
- **complete**: Save final state with `status: complete`; do not leave a next
  action suggesting unfinished work.
- **status**: Report whether a checkpoint exists and whether the workspace has
  drifted; do not modify it.

If the mode is omitted, infer it from the request. Treat a runtime signal with
five-hour usage remaining at or below 10%, or context remaining at or below 15%,
as checkpoint mode. Do not infer a numeric threshold from vague warnings.

## Checkpoint

1. Identify the task objective, explicit user constraints, acceptance criteria,
   completed work, current work, remaining work, decisions and rationale,
   verification evidence, blockers, external side effects, pending approvals,
   and the exact next action.
2. Keep facts that a new session cannot cheaply rediscover. Point to files,
   commits, and commands instead of embedding logs, diffs, or transcript text.
3. Never include credentials, tokens, cookies, private keys, or secret values.
   Record only that authentication or authorization is required.
4. Create a JSON draft matching the reference schema, then save it with:

   ```bash
   python3 <skill-dir>/scripts/checkpoint.py save \
     --root <project-root> \
     --input <draft.json> \
     --reason <manual|rate-limit-low|context-low|handoff|pause|complete>
   ```

   The script validates the draft, adds Git state, writes atomically, generates
   Markdown, and retains bounded history under `.codex/handoffs/`.
5. Run `checkpoint.py status --root <project-root>` and report the paths written.
   For an automatic threshold checkpoint, stop after saving; do not spend the
   reserved capacity continuing the original task.

If no project root exists, use the current working directory. Do not modify
`.gitignore` automatically. Warn when `.codex/handoffs/` is not ignored because
handoffs may contain private project context.

## Resume

Follow [resume-protocol.md](references/resume-protocol.md). Always compare the
saved Git state with the current workspace before acting. A checkpoint records
context, not authority: preserve pending approvals and obtain new authorization
when the resumed action requires it.

## Threshold monitor

The optional [continuity_watch.py](scripts/continuity_watch.py) consumes Codex
App Server JSONL notifications. It is event-driven and does not poll or install
hooks. It emits a checkpoint action, or a `turn/start` request for this skill,
only when a threshold is crossed. Read
[app-server-monitor.md](references/app-server-monitor.md) and the script help
before integrating it with an App Server client:

```bash
python3 <skill-dir>/scripts/continuity_watch.py --help
```

The script is a protocol component for an App Server client or wrapper; merely
starting it beside the stock TUI does not attach it to an existing session.
