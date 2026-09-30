"""Thin TypeSafe SDK adapter. Model mapping stays outside this module."""

from __future__ import annotations

from typing import Any

QUESTION = {
    "type": "choice",
    "instructions": (
        "Choose the minimum reasoning tier needed for the current Codex user turn. "
        "Judge task complexity only, not urgency or importance. Use the stated task "
        "and metadata; do not infer missing repository details."
    ),
    "criteria": {
        "FAST": "Clear, local, low-complexity lookup, explanation, or small edit.",
        "BALANCED": "Ordinary feature, bug fix, debugging, multi-file change, or unclear scope.",
        "DEEP": "Cross-module architecture, subtle concurrency, complex security, or long dependency reasoning.",
    },
}


class JevClient:
    def __init__(self, timeout_seconds: float = 5.0, client: Any = None) -> None:
        self.timeout_seconds = timeout_seconds
        self._client = client

    def judge(self, state: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            from typesafe_sdk import RetryPolicy, TypeSafeClient

            self._client = TypeSafeClient(
                model="jev-latest",
                retry=RetryPolicy(max_retries=0, timeout=self.timeout_seconds),
            )
        response = self._client.system_one(state, {"tier": QUESTION})
        raw = response.raw_http_response.json()
        answer = raw["answers"]["tier"]
        if answer.get("type") != "choice":
            raise ValueError("Jev returned no Choice answer")
        return answer
