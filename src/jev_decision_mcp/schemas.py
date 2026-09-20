"""Validated inputs and structured outputs for the MCP tools."""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


QuestionContent = str | list[Any] | dict[str, Any]
State = str | list[Any] | dict[str, Any]
RiskClass = Literal["advisory", "reversible", "consequential"]
DecisionStatus = Literal["decided", "uncertain", "review_required"]
BatchStatus = Literal["completed"]


def _validate_json_content(value: Any, label: str) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be JSON-serializable") from error
    if len(encoded) > 200_000:
        raise ValueError(f"{label} exceeds the 200,000-character limit")
    return value


class QuestionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: QuestionContent

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: QuestionContent) -> QuestionContent:
        return _validate_json_content(value, "instructions")


class ChoiceQuestion(QuestionBase):
    type: Literal["choice"]
    criteria: dict[str, Any | None]

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value: dict[str, Any | None]) -> dict[str, Any | None]:
        if not 2 <= len(value) <= 255:
            raise ValueError("Choice criteria must contain 2 to 255 options")
        if any(not key.strip() for key in value):
            raise ValueError("Choice option names cannot be empty")
        return _validate_json_content(value, "Choice criteria")


class NoulCriteria(BaseModel):
    """Noul meanings, accepting friendly yes/no aliases at the MCP boundary."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    when_true: Any | None = Field(default=None, alias="true")
    when_false: Any | None = Field(default=None, alias="false")

    @model_validator(mode="before")
    @classmethod
    def normalize_yes_no(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        aliases = {
            "true": "true",
            "yes": "true",
            "false": "false",
            "no": "false",
        }
        normalized: dict[str, Any] = {}
        for raw_key, meaning in value.items():
            key = str(raw_key).strip().lower()
            canonical = aliases.get(key)
            if canonical is None:
                raise ValueError(
                    "Noul criteria may contain true/false or yes/no keys"
                )
            if canonical in normalized:
                raise ValueError(f"Duplicate Noul criterion for {canonical!r}")
            normalized[canonical] = meaning
        return _validate_json_content(normalized, "Noul criteria")


class NoulQuestion(QuestionBase):
    type: Literal["noul"]
    criteria: NoulCriteria | None = None


class ScoreQuestion(QuestionBase):
    type: Literal["score"]
    criteria: list[Any] = Field(min_length=2, max_length=10)

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value: list[Any]) -> list[Any]:
        return _validate_json_content(value, "Score criteria")


Question = Annotated[
    ChoiceQuestion | NoulQuestion | ScoreQuestion,
    Field(discriminator="type"),
]


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: State
    questions: dict[str, Question] = Field(min_length=1, max_length=128)
    action_question_id: str
    risk_class: RiskClass = "reversible"
    review_if_noul_at_least: dict[str, float] = Field(default_factory=dict)

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: State) -> State:
        return _validate_json_content(value, "state")

    @field_validator("action_question_id")
    @classmethod
    def validate_action_question_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action_question_id cannot be empty")
        return value

    @field_validator("review_if_noul_at_least")
    @classmethod
    def validate_noul_thresholds(cls, value: dict[str, float]) -> dict[str, float]:
        for question_id, threshold in value.items():
            if not question_id.strip():
                raise ValueError("Noul blocker question ids cannot be empty")
            if not math.isfinite(threshold) or not 0 <= threshold <= 1:
                raise ValueError("Noul blocker thresholds must be between 0 and 1")
        return value


class BatchItem(BaseModel):
    """One independently judged item in a homogeneous batch."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    state: State

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Batch item id cannot be blank")
        return normalized

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: State) -> State:
        return _validate_json_content(value, "Batch item state")


class BatchJudgmentInput(BaseModel):
    """Apply one typed semantic question independently to many items."""

    model_config = ConfigDict(extra="forbid")

    items: list[BatchItem] = Field(min_length=1, max_length=128)
    question: Question

    @model_validator(mode="after")
    def validate_batch(self) -> "BatchJudgmentInput":
        item_ids = [item.id for item in self.items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Batch item ids must be unique")
        _validate_json_content(
            [item.model_dump(mode="json") for item in self.items],
            "Batch items",
        )
        return self

class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class DecisionResult(BaseModel):
    status: DecisionStatus
    action: str | None
    candidate_action: str
    confidence: float
    probabilities: dict[str, float]
    answers: dict[str, Any]
    uncertainty: list[str]
    model: str
    policy_version: str
    latency_ms: float
    usage: Usage
    request_id: str | None = None


class BatchItemResult(BaseModel):
    id: str
    answer: dict[str, Any]


class BatchJudgmentResult(BaseModel):
    status: BatchStatus = "completed"
    results: list[BatchItemResult]
    model: str
    latency_ms: float
    usage: Usage
    request_id: str | None = None
