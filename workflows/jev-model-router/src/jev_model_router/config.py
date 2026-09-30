"""Validated local routing configuration."""

from __future__ import annotations

from pathlib import Path
import tomllib
from typing import Any

from .policy import TIERS


def load_config(path: Path) -> dict[str, Any]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    mode = data.get("mode", "shadow")
    threshold = data.get("confidence_threshold", 0.8)
    timeout = data.get("jev_timeout_seconds", 5.0)
    tiers = data.get("tiers", {})
    if mode not in ("shadow", "route"):
        raise ValueError("mode must be shadow or route")
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise ValueError("confidence_threshold must be between 0 and 1")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("jev_timeout_seconds must be positive")
    if set(tiers) != set(TIERS):
        raise ValueError("tiers must define FAST, BALANCED, and DEEP")
    for tier in TIERS:
        value = tiers[tier]
        if not isinstance(value, dict) or not all(
            isinstance(value.get(key), str) and value[key].strip() for key in ("model", "effort")
        ):
            raise ValueError(f"{tier} needs model and effort")
    data["mode"] = mode
    data["confidence_threshold"] = float(threshold)
    data["jev_timeout_seconds"] = float(timeout)
    data["telemetry_path"] = str((path.parent / data.get("telemetry_path", "router-events.jsonl")).resolve())
    return data
