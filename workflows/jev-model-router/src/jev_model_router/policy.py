"""Confidence gate and configured model mapping."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

TIERS = ("FAST", "BALANCED", "DEEP")


@dataclass(frozen=True)
class Route:
    tier: str
    confidence: float | None
    probabilities: dict[str, float] | None
    model: str
    effort: str
    fallback_reason: str | None = None


def choose_route(
    answer: dict[str, Any] | None,
    tiers: dict[str, dict[str, str]],
    threshold: float,
    error: str | None = None,
) -> Route:
    reason = error
    choice: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    if reason is None:
        try:
            if not isinstance(answer, dict):
                raise ValueError("missing answer")
            choice = answer["choice"]
            confidence = float(answer["confidence"])
            raw_probs = answer["probabilities"]
            probabilities = {str(k): float(v) for k, v in raw_probs.items()}
            if (
                answer.get("type") != "choice"
                or choice not in TIERS
                or not math.isfinite(confidence)
                or not 0 <= confidence <= 1
                or set(probabilities) != set(TIERS)
                or any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values())
            ):
                raise ValueError("invalid answer")
            if confidence < threshold:
                reason = "low_confidence"
        except (KeyError, TypeError, ValueError):
            reason = "invalid_response"
    selected = choice if reason is None else "BALANCED"
    mapping = tiers[selected]
    return Route(selected, confidence, probabilities, mapping["model"], mapping["effort"], reason)
