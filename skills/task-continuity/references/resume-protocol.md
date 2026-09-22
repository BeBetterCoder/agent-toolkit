# Resume protocol

Use this reference only when restoring or inspecting a checkpoint.

## Locate and inspect

1. Run:

   ```bash
   python3 <skill-dir>/scripts/checkpoint.py status --root <project-root>
   ```

2. Read `.codex/handoffs/latest.md` first. Read `latest.json` when exact fields,
   machine state, or authorization boundaries matter.
3. If no checkpoint exists, say so. Do not reconstruct one from guesses.

## Detect drift

Compare the saved and current Git branch, HEAD, dirty state, changed paths,
required files, and relevant background or external state. Classify drift as:

- **none**: recorded state still matches;
- **expected**: changes directly continue the recorded work;
- **conflicting**: files, commits, branch, or external state invalidate the
  recorded next action.

Report conflicting drift before editing. Never overwrite newer work merely to
match the checkpoint.

## Continue

Restate the objective, completed work that must not be repeated, constraints,
pending approvals, detected drift, and next action. Continue from
`resume.next_action` only when it remains safe and within the original scope. A
checkpoint transfers knowledge, not credentials or expanded authority.

If `status` is `complete`, report the saved completion and verification rather
than restarting work. If it is `blocked`, re-check the blocker once before
asking for input.
