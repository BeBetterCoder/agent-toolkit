"""Thin TypeSafe SDK adapter. Model mapping stays outside this module."""

from __future__ import annotations

from typing import Any

QUESTION = {
    "type": "choice",
    "instructions": (
        "Classify the Codex model capability and reasoning effort needed for the current "
        "user task as FAST, BALANCED, or DEEP. Choose the least demanding tier that can "
        "complete the task reliably. Use FAST for direct explanations, file or symbol "
        "lookups, typo fixes, small documentation or configuration edits, and clearly "
        "scoped code changes that require little investigation. Use BALANCED for routine "
        "feature development, bug fixes, failing-test diagnosis, API adjustments, "
        "related multi-file changes, and moderate refactoring that require investigation "
        "and verification. Use DEEP for cross-module architecture work, subtle concurrency "
        "or asynchronous lifecycle problems, security analysis requiring causal tracing, "
        "and difficult debugging involving several interacting components or competing "
        "hypotheses. Judge the reasoning and dependency depth required by the task, rather "
        "than its keywords, length, urgency, or importance. Base the decision only on the "
        "task and metadata provided."
    ),
    "criteria": {
        "FAST": "Direct explanation, lookup, typo fix, small documentation or configuration edit, or clearly scoped local code change.",
        "BALANCED": "Routine feature, bug fix, failing-test diagnosis, API adjustment, related multi-file change, or moderate refactor.",
        "DEEP": "Cross-module architecture, subtle concurrency or asynchronous lifecycle problem, causal security analysis, or difficult multi-component debugging.",
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
