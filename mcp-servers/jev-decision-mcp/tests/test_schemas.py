from __future__ import annotations

import pytest
from pydantic import ValidationError

from jev_decision_mcp.schemas import BatchJudgmentInput, DecisionInput


def test_choice_requires_at_least_two_options() -> None:
    with pytest.raises(ValidationError, match="2 to 255"):
        DecisionInput(
            state="A task",
            questions={
                "action": {
                    "type": "choice",
                    "instructions": "Choose.",
                    "criteria": {"only": None},
                }
            },
            action_question_id="action",
        )


def test_score_accepts_two_to_ten_levels() -> None:
    parsed = DecisionInput(
        state="A task",
        questions={
            "action": {
                "type": "choice",
                "instructions": "Choose.",
                "criteria": {"yes": None, "no": None},
            },
            "risk": {
                "type": "score",
                "instructions": "Rate risk.",
                "criteria": ["low", "medium", "high"],
            },
        },
        action_question_id="action",
    )

    assert parsed.questions["risk"].type == "score"


def test_noul_threshold_must_be_probability() -> None:
    with pytest.raises(ValidationError, match="between 0 and 1"):
        DecisionInput(
            state="A task",
            questions={
                "action": {
                    "type": "choice",
                    "instructions": "Choose.",
                    "criteria": {"yes": None, "no": None},
                }
            },
            action_question_id="action",
            review_if_noul_at_least={"block": 1.1},
        )


@pytest.mark.parametrize(
    ("criteria", "expected"),
    [
        (
            {"yes": "There are multiple issues.", "no": "There is one issue."},
            {"true": "There are multiple issues.", "false": "There is one issue."},
        ),
        (
            {"true": "There are multiple issues.", "false": "There is one issue."},
            {"true": "There are multiple issues.", "false": "There is one issue."},
        ),
        (
            {"YES": "There are multiple issues.", "NO": "There is one issue."},
            {"true": "There are multiple issues.", "false": "There is one issue."},
        ),
    ],
)
def test_noul_criteria_aliases_are_normalized(
    criteria: dict[str, str], expected: dict[str, str]
) -> None:
    parsed = DecisionInput(
        state="A task",
        questions={
            "action": {
                "type": "choice",
                "instructions": "Choose.",
                "criteria": {"yes": None, "no": None},
            },
            "multiple_issues": {
                "type": "noul",
                "instructions": "Are there multiple independent issues?",
                "criteria": criteria,
            },
        },
        action_question_id="action",
    )

    dumped = parsed.questions["multiple_issues"].model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    assert dumped["criteria"] == expected


def test_noul_criteria_reject_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="true/false or yes/no"):
        DecisionInput(
            state="A task",
            questions={
                "action": {
                    "type": "choice",
                    "instructions": "Choose.",
                    "criteria": {"yes": None, "no": None},
                },
                "blocker": {
                    "type": "noul",
                    "instructions": "Should this block?",
                    "criteria": {"maybe": "Unclear."},
                },
            },
            action_question_id="action",
        )


def test_batch_requires_unique_item_ids() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        BatchJudgmentInput(
            items=[
                {"id": "duplicate", "state": "first"},
                {"id": "duplicate", "state": "second"},
            ],
            question={
                "type": "choice",
                "instructions": "Classify the item.",
                "criteria": {"keep": None, "discard": None},
            },
        )
