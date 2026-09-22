# Contributing

Keep each tool self-contained and document its runtime, setup, test, and release
commands in the tool's own `README.md`.

- Put reusable Agent skills in `skills/`.
- Put MCP server implementations in `mcp-servers/`.
- Put orchestrated, multi-step processes in `workflows/`.
- Put standalone prompt templates in `prompts/`.
- Keep secrets and machine-specific paths out of `configs/`.
- Add runnable usage scenarios to `examples/`.

Run the tests and formatting checks defined by the affected subproject before
opening a pull request.
