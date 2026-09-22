from __future__ import annotations

import os
import sys

import pytest
from mcp import Client, StdioServerParameters

from jev_decision_mcp.server import mcp


@pytest.mark.anyio
async def test_policy_tool_returns_structured_content() -> None:
    async with Client(mcp) as client:
        tool_page = await client.list_tools()
        result = await client.call_tool("jev_list_policies", {})

    by_name = {tool.name: tool for tool in tool_page.tools}
    assert set(by_name) == {
        "jev_decide",
        "jev_judge_batch",
        "jev_list_policies",
    }
    assert by_name["jev_decide"].title == "Jev bounded decision"
    assert by_name["jev_judge_batch"].title == "Jev batch judgment"
    assert by_name["jev_list_policies"].title == "Jev decision policies"
    decision_schema = by_name["jev_decide"].input_schema
    assert set(decision_schema["required"]) == {
        "state",
        "questions",
        "action_question_id",
    }
    batch_schema = by_name["jev_judge_batch"].input_schema
    assert set(batch_schema["required"]) == {"items", "question"}

    decision_annotations = by_name["jev_decide"].annotations
    batch_annotations = by_name["jev_judge_batch"].annotations
    policy_annotations = by_name["jev_list_policies"].annotations
    assert decision_annotations is not None
    assert batch_annotations is not None
    assert policy_annotations is not None
    assert decision_annotations.read_only_hint is False
    assert decision_annotations.destructive_hint is False
    assert decision_annotations.idempotent_hint is True
    assert decision_annotations.open_world_hint is True
    assert batch_annotations == decision_annotations
    assert policy_annotations.read_only_hint is True
    assert policy_annotations.destructive_hint is False
    assert policy_annotations.idempotent_hint is True
    assert policy_annotations.open_world_hint is False

    assert not result.is_error
    assert result.structured_content["policy_version"] == "decision-gate-v1"
    assert set(result.structured_content["policies"]) == {
        "advisory",
        "reversible",
        "consequential",
    }


@pytest.mark.anyio
async def test_stdio_server_exposes_policy_tool() -> None:
    environment = os.environ.copy()
    environment["TYPESAFE_LOG_LEVEL"] = "warning"
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jev_decision_mcp.server"],
        env=environment,
    )

    async with Client(parameters) as client:
        result = await client.call_tool("jev_list_policies", {})

    assert not result.is_error
    assert result.structured_content["policy_version"] == "decision-gate-v1"
