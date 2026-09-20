from __future__ import annotations

import os
import sys

import pytest
from mcp import Client, StdioServerParameters


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_TYPESAFE_INTEGRATION") != "1",
    reason="set RUN_TYPESAFE_INTEGRATION=1 to call the real TypeSafe API",
)


@pytest.mark.anyio
async def test_live_decision_through_mcp() -> None:
    environment = os.environ.copy()
    environment["TYPESAFE_LOG_LEVEL"] = "warning"
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jev_decision_mcp.server"],
        env=environment,
    )

    async with Client(parameters) as client:
        result = await client.call_tool(
            "jev_decide",
            {
                "state": {
                    "task": "Production checkout is down and every order is failing.",
                },
                "questions": {
                    "action": {
                        "type": "choice",
                        "instructions": "Choose the best next action for `task`.",
                        "criteria": {
                            "fix_now": "An active production incident needs immediate work.",
                            "investigate": "There may be an issue but more evidence is required.",
                            "needs_clarification": "Essential information is missing.",
                            "no_action": "There is no unresolved issue.",
                        },
                    },
                    "active_incident": {
                        "type": "noul",
                        "instructions": "Does `task` describe an active production incident?",
                        "criteria": {
                            "yes": "An active production incident is described.",
                            "no": "No active production incident is described.",
                        },
                    },
                },
                "action_question_id": "action",
                "risk_class": "reversible",
            },
        )

    assert not result.is_error
    content = result.structured_content
    assert content["status"] == "decided"
    assert content["action"] == "fix_now"
    assert content["model"].startswith("jev-")
    assert content["usage"]["input_tokens"] > 0


@pytest.mark.anyio
async def test_live_batch_judgment_through_mcp() -> None:
    environment = os.environ.copy()
    environment["TYPESAFE_LOG_LEVEL"] = "warning"
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jev_decision_mcp.server"],
        env=environment,
    )

    async with Client(parameters) as client:
        result = await client.call_tool(
            "jev_judge_batch",
            {
                "items": [
                    {"id": "a", "state": "I was charged twice."},
                    {"id": "b", "state": "The app crashes when it opens."},
                ],
                "question": {
                    "type": "choice",
                    "instructions": "Route this support request.",
                    "criteria": {
                        "billing": "Payment, invoice, refund, or charge issue.",
                        "technical": "Software behavior or reliability issue.",
                    },
                },
            },
        )

    assert not result.is_error
    content = result.structured_content
    assert content["status"] == "completed"
    assert [item["id"] for item in content["results"]] == ["a", "b"]
    assert content["results"][0]["answer"]["choice"] == "billing"
    assert content["results"][1]["answer"]["choice"] == "technical"
    assert content["usage"]["input_tokens"] > 0
