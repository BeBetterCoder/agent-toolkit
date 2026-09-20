"""TypeSafe SDK adapter plus confidence and blocker gating."""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

from typesafe_sdk import RetryPolicy, TypeSafeAPIError, TypeSafeClient

from .policies import POLICIES, POLICY_VERSION
from .schemas import (
    BatchItemResult,
    BatchJudgmentInput,
    BatchJudgmentResult,
    DecisionInput,
    DecisionResult,
    Usage,
)


class SystemOneClient(Protocol):
    def system_one(self, state: Any, questions: dict[str, Any]) -> Any: ...


class DecisionServiceError(RuntimeError):
    """A sanitized error safe to expose as an MCP tool failure."""


class DecisionEvaluator:
    def __init__(self, client: SystemOneClient | None = None) -> None:
        self._client = client

    def _get_client(self) -> SystemOneClient:
        if self._client is None:
            self._client = TypeSafeClient(
                model=os.environ.get("TYPESAFE_DEFAULT_MODEL", "jev-latest"),
                retry=RetryPolicy(max_retries=2, backoff_max=0.2, timeout=5.0),
            )
        return self._client

    def evaluate(self, decision: DecisionInput) -> DecisionResult:
        questions = {
            question_id: question.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            for question_id, question in decision.questions.items()
        }
        action_question = decision.questions.get(decision.action_question_id)
        if action_question is None:
            raise DecisionServiceError(
                f"Unknown action_question_id: {decision.action_question_id!r}"
            )
        if action_question.type != "choice":
            raise DecisionServiceError("action_question_id must reference a Choice question")

        for question_id in decision.review_if_noul_at_least:
            question = decision.questions.get(question_id)
            if question is None:
                raise DecisionServiceError(f"Unknown Noul blocker question: {question_id!r}")
            if question.type != "noul":
                raise DecisionServiceError(
                    f"Noul blocker {question_id!r} must reference a Noul question"
                )

        started = time.perf_counter()
        try:
            response = self._get_client().system_one(decision.state, questions)
        except TypeSafeAPIError as error:
            status = getattr(error, "status", "unknown")
            request_id = getattr(error, "request_id", None)
            suffix = f"; request_id={request_id}" if request_id else ""
            raise DecisionServiceError(f"TypeSafe API error {status}{suffix}") from error
        except Exception as error:
            raise DecisionServiceError(
                f"TypeSafe request failed: {type(error).__name__}"
            ) from error
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        raw = response.raw_http_response.json()
        answers = raw.get("answers", {})
        action_answer = answers.get(decision.action_question_id)
        if not isinstance(action_answer, dict) or action_answer.get("type") != "choice":
            raise DecisionServiceError("TypeSafe response is missing the action Choice answer")

        candidate_action = action_answer.get("choice")
        confidence = action_answer.get("confidence")
        probabilities = action_answer.get("probabilities")
        if not isinstance(candidate_action, str):
            raise DecisionServiceError("TypeSafe action Choice has no selected option")
        if not isinstance(confidence, (int, float)):
            raise DecisionServiceError("TypeSafe action Choice has no confidence")
        if not isinstance(probabilities, dict):
            raise DecisionServiceError("TypeSafe action Choice has no probability distribution")

        policy = POLICIES[decision.risk_class]
        uncertainty: list[str] = []
        status = "decided"

        if not policy.automatic:
            status = "review_required"
            uncertainty.append("consequential_action_requires_review")
        elif policy.confidence_threshold is not None and confidence < policy.confidence_threshold:
            status = "uncertain"
            uncertainty.append("low_action_confidence")

        if candidate_action == "needs_clarification":
            if status != "review_required":
                status = "uncertain"
            uncertainty.append("needs_clarification")

        for question_id, threshold in decision.review_if_noul_at_least.items():
            answer = answers.get(question_id)
            if not isinstance(answer, dict) or answer.get("type") != "noul":
                raise DecisionServiceError(
                    f"TypeSafe response is missing Noul blocker {question_id!r}"
                )
            if answer.get("noul", 0) >= threshold:
                if status != "review_required":
                    status = "uncertain"
                uncertainty.append(f"blocking_noul:{question_id}")

        usage = raw.get("usage") or {}
        return DecisionResult(
            status=status,
            action=candidate_action if status == "decided" else None,
            candidate_action=candidate_action,
            confidence=float(confidence),
            probabilities={key: float(value) for key, value in probabilities.items()},
            answers=answers,
            uncertainty=uncertainty,
            model=str(raw.get("model", "unknown")),
            policy_version=POLICY_VERSION,
            latency_ms=latency_ms,
            usage=Usage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            ),
            request_id=getattr(response, "request_id", None),
        )

    def evaluate_batch(self, batch: BatchJudgmentInput) -> BatchJudgmentResult:
        """Apply one question template to many independent items in one request."""

        combined_state = {
            "items": [
                {"id": item.id, "state": item.state}
                for item in batch.items
            ]
        }
        question_template = batch.question.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        questions: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(batch.items):
            question = dict(question_template)
            question["instructions"] = {
                "task": question_template["instructions"],
                "scope": (
                    f"Apply the task only to `items[{index}].state`, whose item id "
                    f"is {item.id!r}. Do not judge any other item for this answer."
                ),
            }
            questions[f"item_{index}"] = question

        started = time.perf_counter()
        try:
            response = self._get_client().system_one(combined_state, questions)
        except TypeSafeAPIError as error:
            status = getattr(error, "status", "unknown")
            request_id = getattr(error, "request_id", None)
            suffix = f"; request_id={request_id}" if request_id else ""
            raise DecisionServiceError(f"TypeSafe API error {status}{suffix}") from error
        except Exception as error:
            raise DecisionServiceError(
                f"TypeSafe request failed: {type(error).__name__}"
            ) from error
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        raw = response.raw_http_response.json()
        answers = raw.get("answers", {})
        expected_type = batch.question.type
        results: list[BatchItemResult] = []
        for index, item in enumerate(batch.items):
            answer = answers.get(f"item_{index}")
            if not isinstance(answer, dict) or answer.get("type") != expected_type:
                raise DecisionServiceError(
                    f"TypeSafe response is missing the {expected_type} answer for "
                    f"batch item {item.id!r}"
                )
            results.append(BatchItemResult(id=item.id, answer=answer))

        usage = raw.get("usage") or {}
        return BatchJudgmentResult(
            results=results,
            model=str(raw.get("model", "unknown")),
            latency_ms=latency_ms,
            usage=Usage(
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            ),
            request_id=getattr(response, "request_id", None),
        )
