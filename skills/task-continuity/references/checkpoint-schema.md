# Checkpoint schema

Use this reference only when creating or completing a checkpoint.

The JSON draft is the source of truth. The save script enriches it with a
checkpoint ID, timestamp, trigger details, and current Git state, then renders
`latest.md`. Keep the draft concise; prefer paths and evidence over copied data.

## Draft shape

```json
{
  "status": "active",
  "task": {
    "objective": "The concrete outcome the user wants",
    "user_intent": ["Important intent that must survive a new session"],
    "constraints": ["Explicit requirements and prohibitions"],
    "non_goals": ["Work intentionally outside scope"],
    "acceptance_criteria": ["Observable completion condition"]
  },
  "progress": {
    "current_state": "Short description of where the work stands",
    "completed": ["Completed result with evidence or path"],
    "in_progress": ["Partially completed work"],
    "remaining": ["Ordered remaining work"],
    "do_not_repeat": ["Expensive or harmful work already performed"]
  },
  "decisions": [
    {
      "decision": "Decision that must be preserved",
      "rationale": "Why it was chosen",
      "alternatives_rejected": ["Alternative and why it lost"]
    }
  ],
  "verification": {
    "passed": ["Command or check and its result"],
    "failed": ["Failure that remains relevant"],
    "not_run": ["Important check still required"]
  },
  "runtime": {
    "background_processes": ["Process plus session identifier, never a secret"],
    "external_changes": ["Remote or external side effect already performed"],
    "pending_approvals": ["Action that still requires authorization"],
    "blockers": ["Concrete blocker"]
  },
  "resume": {
    "next_action": "One specific first action for the new session",
    "files_to_read_first": ["Relative path"],
    "commands_to_run_first": ["Safe read-only or verification command"],
    "open_questions": ["Unresolved question"],
    "resume_prompt": "Brief ready-to-use continuation instruction"
  }
}
```

## Rules

- `status` is `active`, `paused`, `blocked`, or `complete`.
- `task.objective`, `progress.current_state`, and `resume.next_action` are
  required non-empty strings. For a completed task, use `"No further action"`.
- All paths should be project-relative when possible.
- `decisions` may contain only `decision`, `rationale`, and
  `alternatives_rejected`.
- Never store raw transcripts, full diffs, large tool outputs, or environment
  variable values.
- Never store passwords, API keys, access tokens, cookies, authorization
  headers, private keys, or credential material.
- Record external mutations separately from local edits so a new session does
  not repeat them.
- Record approvals as pending unless the user has already authorized the exact
  operation and that authorization remains applicable.

The saved JSON adds `schema_version`, `checkpoint_id`, `created_at`, `trigger`,
and `workspace`. Do not add these fields to the draft; the script owns them.
