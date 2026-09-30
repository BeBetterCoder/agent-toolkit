"""Small JSONL record of routing and completed Codex turns."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class Telemetry:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def write(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
