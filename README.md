# Jev Decision MCP

A local STDIO MCP server that lets Codex make bounded semantic decisions with
Jev through TypeSafe. The server validates typed questions, batches them into one
TypeSafe request, applies deterministic confidence gates, and returns a compact
structured decision.

## Tools

- `jev_decide`: evaluate a Choice action plus optional Noul/Score checks.
- `jev_judge_batch`: apply one shared Choice/Noul/Score judgment to as many
  as 128 independent items in one TypeSafe request.
- `jev_list_policies`: inspect the server-side risk gates.

For Noul criteria, the MCP boundary accepts both `true`/`false` and the more
natural `yes`/`no` keys. It always normalizes them to `true`/`false` before
calling TypeSafe.

The tool judges only. It does not edit files, run shell commands, or perform the
selected action.

## Automatic use

The repository includes a lightweight `jev-decision` runtime skill. Users do
not need to mention TypeSafe, MCP, a tool name, or a question schema. Its primary
automatic-use case is fast bulk judgment: many independent items share one semantic
Choice, Noul, or Score definition and need structured results or probabilities.
This covers classification, filtering, labeling, scoring, routing, verification,
and prioritization across domains rather than a fixed set of business workflows.

Obvious one-off decisions, deterministic work, evidence gathering, and open-ended
analysis stay with Codex. The broader `typesafe-ai` skill remains the development
skill for designing or modifying TypeSafe integrations.

## Development

```bash
uv sync --dev
uv run pytest
uv run mcp dev src/jev_decision_mcp/server.py
```

`mcp dev` uses the MCP Inspector and therefore also requires `npx`.

## Run over STDIO

```bash
uv run --frozen jev-decision-mcp
```

No output is expected: the process is waiting for MCP messages on stdin. All
application logging goes to stderr because stdout is the MCP protocol stream.

## Codex

The repository is self-contained for Codex: `.codex/config.toml` registers the
STDIO server with portable, repository-relative paths, `.agents/skills/` contains
the runtime skill, and `AGENTS.md` provides the project routing rule.

Install the locked environment and export your TypeSafe API key before starting
Codex from the repository:

```bash
uv sync --dev
export TYPESAFE_API_KEY="your-key"
codex
```

Trust the project when Codex asks so its project configuration can load. Restart
Codex after the first install, then use `/mcp` to verify that
`jev_decision` exposes all three tools. The config requires `uv` on `PATH`,
forwards only the `TYPESAFE_API_KEY` variable, and does not contain machine-local
paths or proxy overrides.

The two inference tools default to `prompt` approval because they send their
inputs to an external API. If this boundary is acceptable for your workload, you
can override their approval mode to `approve` in your user-level Codex config.
The local `jev_list_policies` tool is pre-approved.

The repository `AGENTS.md` routes runtime judgments to the lightweight skill. A
typical request is now ordinary natural language:

```text
Classify these issues as fix now, investigate, ask the user, or close. Keep
low-confidence cases for review.
```

Use `$jev-decision` only when you want to force the MCP-backed path for
testing or comparison.

## Data handling

`jev_decide` and `jev_judge_batch` forward their state and question
definitions to `https://api.typesafe.ai`. Their MCP annotations therefore mark
them as open-world and not purely read-only, even though they never mutate user
data or perform the selected action. `jev_list_policies` is fully local.

Do not include credentials, secrets, personal data, or irrelevant repository
content. The API key is read from the process environment and is not included in
the request state. Raw state is not logged by this server; consult TypeSafe's own
terms and privacy policy for server-side retention and processing.

## Live integration test

The real-API test is opt-in and uses the exported `TYPESAFE_API_KEY`:

```bash
RUN_TYPESAFE_INTEGRATION=1 uv run pytest tests/test_live.py
```
