"""MCP entrypoint for confidence-gated Jev decisions."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .evaluator import DecisionEvaluator, DecisionServiceError
from .policies import describe_policies
from .schemas import (
    BatchItem,
    BatchJudgmentInput,
    BatchJudgmentResult,
    DecisionInput,
    DecisionResult,
    Question,
    RiskClass,
    State,
)


SERVER_INSTRUCTIONS = (
    "Use this server for fast, typed semantic judgments. The inference tools send "
    "their state and questions to api.typesafe.ai; never include credentials, secrets, "
    "or irrelevant content. Prefer jev_judge_batch when one Choice, Noul, or "
    "Score judgment is applied independently to many items with shared criteria. Use "
    "jev_decide for a single bounded decision whose probabilities control "
    "downstream routing or review. Do not use it for exact calculations, evidence "
    "gathering, or open-ended generation. The tools judge only and never perform actions."
)

mcp = MCPServer(
    "jev-decision",
    version="0.3.0",
    instructions=SERVER_INSTRUCTIONS,
    log_level="WARNING",
)
_evaluator = DecisionEvaluator()

# These hints describe observable behavior to MCP hosts. The inference tools do
# not mutate user data, but they do send their inputs to the external TypeSafe
# API, so they are intentionally not marked read-only and are open-world.
REMOTE_JUDGMENT_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
LOCAL_POLICY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(
    title="Jev bounded decision",
    annotations=REMOTE_JUDGMENT_ANNOTATIONS,
)
def jev_decide(
    state: State,
    questions: dict[str, Question],
    action_question_id: str,
    risk_class: RiskClass = "reversible",
    review_if_noul_at_least: dict[str, float] | None = None,
) -> DecisionResult:
    """Make a bounded, confidence-gated semantic decision.

    Use for repeated or ambiguous routing, ranking, triage, classification,
    selection, or independent verification when typed probabilities change the
    downstream workflow. Do not use for obvious one-off decisions, deterministic
    calculations, evidence gathering, or open-ended reasoning. This tool returns
    a judgment and never executes the selected action. State and questions are
    sent to the external TypeSafe API.
    """

    try:
        decision = DecisionInput(
            state=state,
            questions=questions,
            action_question_id=action_question_id,
            risk_class=risk_class,
            review_if_noul_at_least=review_if_noul_at_least or {},
        )
        return _evaluator.evaluate(decision)
    except DecisionServiceError as error:
        raise ToolError(str(error)) from error


@mcp.tool(
    title="Jev batch judgment",
    annotations=REMOTE_JUDGMENT_ANNOTATIONS,
)
def jev_judge_batch(
    items: list[BatchItem],
    question: Question,
) -> BatchJudgmentResult:
    """Apply one shared typed judgment independently to many items in one API call.

    Use for fast bulk classification, filtering, scoring, routing, labeling,
    verification, or prioritization in any domain. Each item may have different
    state, but every item must use the same Choice, Noul, or Score question and
    criteria. Results preserve item ids and raw typed probabilities. Use separate
    calls when items require different questions or when one answer changes the
    state needed for the next. This tool judges only and performs no action.
    Item states and the shared question are sent to the external TypeSafe API.
    """

    try:
        batch = BatchJudgmentInput(items=items, question=question)
        return _evaluator.evaluate_batch(batch)
    except DecisionServiceError as error:
        raise ToolError(str(error)) from error


@mcp.tool(
    title="Jev decision policies",
    annotations=LOCAL_POLICY_ANNOTATIONS,
)
def jev_list_policies() -> dict[str, Any]:
    """List the deterministic risk gates applied after TypeSafe inference."""

    return describe_policies()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
