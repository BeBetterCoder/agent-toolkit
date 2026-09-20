from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_codex_config_is_portable_and_exposes_every_tool() -> None:
    with (ROOT / ".codex" / "config.toml").open("rb") as stream:
        config = tomllib.load(stream)

    server = config["mcp_servers"]["jev_decision"]
    assert server["command"] == "uv"
    assert server["cwd"] == ".."
    assert server["required"] is False
    assert server["default_tools_approval_mode"] == "prompt"
    assert set(server["enabled_tools"]) == {
        "jev_decide",
        "jev_judge_batch",
        "jev_list_policies",
    }
    assert server["env_vars"] == ["TYPESAFE_API_KEY"]
    assert set(server["env"]) == {"TYPESAFE_LOG_LEVEL"}


def test_runtime_skill_is_part_of_the_repository() -> None:
    assert (ROOT / ".agents" / "skills" / "jev-decision" / "SKILL.md").is_file()
    assert (ROOT / "AGENTS.md").is_file()
