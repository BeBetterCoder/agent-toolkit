"""Keep routing input small and separate from Codex's full turn input."""

from __future__ import annotations

import re
from typing import Any

SECRET_PATTERN = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*)\S+|\bsk-[A-Za-z0-9_-]{12,}\b"
)


def safe_task(text: str, limit: int = 1200) -> str:
    """Redact common credentials and cap the text sent to Jev and telemetry."""
    excerpt = text[:limit]
    return SECRET_PATTERN.sub(lambda match: (match.group(1) or "") + "[REDACTED]", excerpt)


def task_from_turn(params: dict[str, Any]) -> str:
    parts = [
        item.get("text", "")
        for item in params.get("input", [])
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return safe_task("\n".join(parts))


def routing_state(task: str, *, cwd: str | None, previous_failed: bool) -> dict[str, Any]:
    return {
        "task": task,
        "workspace_name": cwd.rstrip("/").split("/")[-1] if cwd else None,
        "previous_turn_failed": previous_failed,
    }
