"""Deterministic policy applied after TypeSafe returns judgments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


POLICY_VERSION = "decision-gate-v1"


@dataclass(frozen=True)
class RiskPolicy:
    automatic: bool
    confidence_threshold: float | None
    description: str


POLICIES: dict[str, RiskPolicy] = {
    "advisory": RiskPolicy(
        automatic=True,
        confidence_threshold=0.70,
        description="Advisory recommendation with no direct external effect.",
    ),
    "reversible": RiskPolicy(
        automatic=True,
        confidence_threshold=0.80,
        description="A low-impact action that is easy to inspect and undo.",
    ),
    "consequential": RiskPolicy(
        automatic=False,
        confidence_threshold=None,
        description="A consequential or difficult-to-reverse action always requires review.",
    ),
}


def describe_policies() -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "policies": {name: asdict(policy) for name, policy in POLICIES.items()},
        "notes": [
            "Thresholds are initial defaults and must be calibrated on representative data.",
            "Confidence measures concentration of the returned distribution, not truth.",
        ],
    }

