"""Per-turn semantic decision; failure always becomes BALANCED."""

from __future__ import annotations

import time
from typing import Any

from .context import routing_state
from .policy import Route, choose_route


class Router:
    def __init__(self, jev: Any, tiers: dict[str, dict[str, str]], threshold: float) -> None:
        self.jev = jev
        self.tiers = tiers
        self.threshold = threshold

    def route(self, task: str, *, cwd: str | None, previous_failed: bool) -> tuple[Route, float]:
        started = time.perf_counter()
        if not task.strip():
            return choose_route(None, self.tiers, self.threshold, "no_text_task"), 0.0
        try:
            answer = self.jev.judge(routing_state(task, cwd=cwd, previous_failed=previous_failed))
            route = choose_route(answer, self.tiers, self.threshold)
        except Exception as exc:
            route = choose_route(None, self.tiers, self.threshold, f"jev_error:{type(exc).__name__}")
        return route, round((time.perf_counter() - started) * 1000, 1)
