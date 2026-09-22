from __future__ import annotations

from typing import Any

import pytest

from jev_decision_mcp.evaluator import DecisionEvaluator, DecisionServiceError
from jev_decision_mcp.schemas import BatchJudgmentInput, DecisionInput


class FakeRawResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeResponse:
    request_id = "req_test"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.raw_http_response = FakeRawResponse(payload)


class FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def system_one(self, state: Any, questions: dict[str, Any]) -> FakeResponse:
        self.calls.append((state, questions))
        return FakeResponse(self.payload)


def payload(confidence: float = 0.95, choice: str = "fix_now", blocker: float = 0.1):
    return {
        "model": "jev-test",
        "answers": {
            "action": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": {
                    "fix_now": confidence,
                    "investigate": round(1 - confidence, 4),
                },
            },
            "multiple_issues": {"type": "noul", "noul": blocker},
        },
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def decision(**overrides: Any) -> DecisionInput:
    values: dict[str, Any] = {
        "state": {"task": "Production checkout is failing."},
        "questions": {
            "action": {
                "type": "choice",
                "instructions": "Choose the next action.",
                "criteria": {
                    "fix_now": "Clear active incident.",
                    "investigate": "More evidence is needed.",
                },
            },
            "multiple_issues": {
                "type": "noul",
                "instructions": "Are there multiple independent issues?",
            },
        },
        "action_question_id": "action",
        "risk_class": "reversible",
    }
    values.update(overrides)
    return DecisionInput(**values)


def test_clear_reversible_decision_is_actionable() -> None:
    client = FakeClient(payload())
    result = DecisionEvaluator(client).evaluate(decision())

    assert result.status == "decided"
    assert result.action == "fix_now"
    assert result.candidate_action == "fix_now"
    assert result.confidence == 0.95
    assert result.request_id == "req_test"
    assert len(client.calls) == 1
    assert set(client.calls[0][1]) == {"action", "multiple_issues"}


def test_low_confidence_is_uncertain() -> None:
    result = DecisionEvaluator(FakeClient(payload(confidence=0.65))).evaluate(decision())

    assert result.status == "uncertain"
    assert result.action is None
    assert result.candidate_action == "fix_now"
    assert "low_action_confidence" in result.uncertainty


def test_consequential_decision_requires_review() -> None:
    result = DecisionEvaluator(FakeClient(payload())).evaluate(
        decision(risk_class="consequential")
    )

    assert result.status == "review_required"
    assert result.action is None
    assert "consequential_action_requires_review" in result.uncertainty


def test_noul_blocker_prevents_action() -> None:
    result = DecisionEvaluator(FakeClient(payload(blocker=0.91))).evaluate(
        decision(review_if_noul_at_least={"multiple_issues": 0.5})
    )

    assert result.status == "uncertain"
    assert result.action is None
    assert "blocking_noul:multiple_issues" in result.uncertainty


def test_needs_clarification_is_never_actionable() -> None:
    raw = payload(choice="needs_clarification")
    raw["answers"]["action"]["probabilities"] = {
        "needs_clarification": 0.95,
        "investigate": 0.05,
    }
    result = DecisionEvaluator(FakeClient(raw)).evaluate(decision())

    assert result.status == "uncertain"
    assert result.action is None
    assert "needs_clarification" in result.uncertainty


def test_action_question_must_be_choice() -> None:
    with pytest.raises(DecisionServiceError, match="must reference a Choice"):
        DecisionEvaluator(FakeClient(payload())).evaluate(
            decision(action_question_id="multiple_issues")
        )


def test_batch_judges_independent_items_in_one_request() -> None:
    client = FakeClient(
        {
            "model": "jev-test",
            "answers": {
                "item_0": {
                    "type": "choice",
                    "choice": "billing",
                    "confidence": 0.93,
                    "probabilities": {"billing": 0.93, "technical": 0.07},
                },
                "item_1": {
                    "type": "choice",
                    "choice": "technical",
                    "confidence": 0.88,
                    "probabilities": {"billing": 0.12, "technical": 0.88},
                },
            },
            "usage": {"input_tokens": 80, "output_tokens": 20},
        }
    )
    batch = BatchJudgmentInput(
        items=[
            {"id": "ticket-a", "state": "I was charged twice."},
            {"id": "ticket-b", "state": "The app crashes on launch."},
        ],
        question={
            "type": "choice",
            "instructions": "Route this support request.",
            "criteria": {"billing": None, "technical": None},
        },
    )

    result = DecisionEvaluator(client).evaluate_batch(batch)

    assert result.status == "completed"
    assert [item.id for item in result.results] == ["ticket-a", "ticket-b"]
    assert result.results[0].answer["choice"] == "billing"
    assert result.results[1].answer["choice"] == "technical"
    assert len(client.calls) == 1
    sent_state, sent_questions = client.calls[0]
    assert sent_state["items"][1]["id"] == "ticket-b"
    assert set(sent_questions) == {"item_0", "item_1"}
    assert "`items[0].state`" in sent_questions["item_0"]["instructions"]["scope"]
