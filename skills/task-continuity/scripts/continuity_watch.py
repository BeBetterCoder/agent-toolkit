#!/usr/bin/env python3
"""Convert Codex App Server usage notifications into checkpoint triggers.

Read JSON-RPC messages from stdin and write actions or turn/start requests to
stdout. A client or wrapper must route messages between this process and the
same App Server; this script does not attach itself to the stock TUI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WatchState:
    rate_windows: set[str] = field(default_factory=set)
    context_triggered: set[str] = field(default_factory=set)
    active_turns: dict[str, str] = field(default_factory=dict)
    pending: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    last_thread_id: str | None = None
    rate_cache: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None) -> "WatchState":
        if path is None or not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                rate_windows=set(raw.get("rate_windows", [])),
                context_triggered=set(raw.get("context_triggered", [])),
                last_thread_id=raw.get("last_thread_id"),
                rate_cache=raw.get("rate_cache", {}),
            )
        except (OSError, json.JSONDecodeError, TypeError):
            return cls()

    def save(self, path: Path | None) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "rate_windows": sorted(self.rate_windows),
                "context_triggered": sorted(self.context_triggered),
                "last_thread_id": self.last_thread_id,
                "rate_cache": self.rate_cache,
            },
            indent=2,
        ) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


class ContinuityWatcher:
    def __init__(
        self,
        *,
        rate_remaining: float = 10,
        context_remaining: float = 15,
        five_hour_minutes: int = 300,
        default_thread_id: str | None = None,
        output_mode: str = "action",
        skill_path: str | None = None,
        state: WatchState | None = None,
    ) -> None:
        self.rate_remaining = rate_remaining
        self.context_remaining = context_remaining
        self.five_hour_minutes = five_hour_minutes
        self.default_thread_id = default_thread_id
        self.output_mode = output_mode
        self.skill_path = skill_path
        self.state = state or WatchState()

    @staticmethod
    def thread_id(params: dict[str, Any]) -> str | None:
        if isinstance(params.get("threadId"), str):
            return params["threadId"]
        thread = params.get("thread")
        if isinstance(thread, dict) and isinstance(thread.get("id"), str):
            return thread["id"]
        turn = params.get("turn")
        if isinstance(turn, dict) and isinstance(turn.get("threadId"), str):
            return turn["threadId"]
        return None

    def target_thread(self, params: dict[str, Any]) -> str | None:
        return self.thread_id(params) or self.default_thread_id or self.state.last_thread_id

    def output(self, triggers: list[dict[str, Any]], thread_id: str | None) -> dict[str, Any]:
        reasons = sorted({item["reason"] for item in triggers})
        if self.output_mode == "action" or not thread_id:
            return {"action": "checkpoint", "threadId": thread_id, "reasons": reasons, "signals": triggers}
        if not self.skill_path:
            raise ValueError("--skill-path is required with --output-mode turn-start")
        reason_arg = "+".join(reasons)
        return {
            "method": "turn/start",
            "id": f"task-continuity:{uuid.uuid4().hex}",
            "params": {
                "threadId": thread_id,
                "input": [
                    {
                        "type": "text",
                        "text": f"$task-continuity checkpoint --reason={reason_arg}. Save the handoff and stop; do not continue the original task.",
                    },
                    {"type": "skill", "name": "task-continuity", "path": self.skill_path},
                ],
            },
        }

    def queue_or_emit(self, trigger: dict[str, Any], thread_id: str | None) -> list[dict[str, Any]]:
        trigger["threadId"] = thread_id
        if thread_id and thread_id in self.state.active_turns:
            self.state.pending.setdefault(thread_id, []).append(trigger)
            return []
        return [self.output([trigger], thread_id)]

    def rate_triggers(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        snapshots = []
        if isinstance(params.get("rateLimits"), dict):
            snapshots.append(params["rateLimits"])
        if isinstance(params.get("rateLimitsByLimitId"), dict):
            snapshots.extend(value for value in params["rateLimitsByLimitId"].values() if isinstance(value, dict))

        found = []
        for snapshot in snapshots:
            limit_id = str(snapshot.get("limitId") or "codex")
            for slot in ("primary", "secondary"):
                window = snapshot.get(slot)
                if not isinstance(window, dict):
                    continue
                cache_key = f"{limit_id}:{slot}"
                merged = {**self.state.rate_cache.get(cache_key, {}), **window}
                self.state.rate_cache[cache_key] = merged
                window = merged
                if window.get("windowDurationMins") != self.five_hour_minutes:
                    continue
                used = window.get("usedPercent")
                if not isinstance(used, (int, float)):
                    continue
                remaining = max(0.0, 100.0 - float(used))
                resets_at = window.get("resetsAt")
                key = f"{limit_id}:{slot}:{resets_at}"
                if remaining > self.rate_remaining:
                    self.state.rate_windows.discard(key)
                if remaining <= self.rate_remaining and key not in self.state.rate_windows:
                    self.state.rate_windows.add(key)
                    found.append(
                        {
                            "reason": "rate-limit-low",
                            "remainingPercent": remaining,
                            "windowDurationMins": self.five_hour_minutes,
                            "resetsAt": resets_at,
                            "limitId": limit_id,
                            "slot": slot,
                        }
                    )
        return found

    def context_trigger(self, params: dict[str, Any]) -> dict[str, Any] | None:
        thread_id = self.thread_id(params)
        usage = params.get("tokenUsage")
        if not thread_id or not isinstance(usage, dict):
            return None
        self.state.last_thread_id = thread_id
        window, last = usage.get("modelContextWindow"), usage.get("last")
        if not isinstance(window, (int, float)) or window <= 0 or not isinstance(last, dict):
            return None
        used = last.get("totalTokens")
        if not isinstance(used, (int, float)):
            return None
        remaining = max(0.0, (float(window) - float(used)) / float(window) * 100.0)
        if remaining > self.context_remaining:
            self.state.context_triggered.discard(thread_id)
            return None
        if thread_id in self.state.context_triggered:
            return None
        self.state.context_triggered.add(thread_id)
        return {
            "reason": "context-low",
            "remainingPercent": remaining,
            "modelContextWindow": window,
            "lastTotalTokens": used,
        }

    def process(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        method, params = message.get("method"), message.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            return []
        thread_id = self.thread_id(params)
        if thread_id:
            self.state.last_thread_id = thread_id

        if method == "turn/started":
            turn = params.get("turn")
            turn_id = turn.get("id") if isinstance(turn, dict) else params.get("turnId")
            if thread_id and isinstance(turn_id, str):
                self.state.active_turns[thread_id] = turn_id
            return []
        if method == "turn/completed":
            if thread_id:
                self.state.active_turns.pop(thread_id, None)
                pending = self.state.pending.pop(thread_id, [])
                return [self.output(pending, thread_id)] if pending else []
            return []
        if method == "item/completed":
            item = params.get("item")
            if thread_id and isinstance(item, dict) and item.get("type") == "contextCompaction":
                self.state.context_triggered.discard(thread_id)
            return []
        if method == "thread/tokenUsage/updated":
            trigger = self.context_trigger(params)
            return self.queue_or_emit(trigger, thread_id) if trigger else []
        if method == "account/rateLimits/updated":
            outputs = []
            target = self.target_thread(params)
            for trigger in self.rate_triggers(params):
                outputs.extend(self.queue_or_emit(trigger, target))
            return outputs
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate-remaining", type=float, default=10.0)
    parser.add_argument("--context-remaining", type=float, default=15.0)
    parser.add_argument("--five-hour-minutes", type=int, default=300)
    parser.add_argument("--thread-id", help="thread used for account-wide rate-limit events")
    parser.add_argument("--output-mode", choices=("action", "turn-start"), default="action")
    parser.add_argument("--skill-path", help="absolute SKILL.md path for turn-start output")
    parser.add_argument("--state-file", type=Path, help="optional deduplication state across restarts")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 0 <= args.rate_remaining <= 100 or not 0 <= args.context_remaining <= 100:
        print("error: thresholds must be between 0 and 100", file=sys.stderr)
        return 2
    if args.output_mode == "turn-start" and not args.skill_path:
        print("error: --skill-path is required with --output-mode turn-start", file=sys.stderr)
        return 2
    state = WatchState.load(args.state_file)
    watcher = ContinuityWatcher(
        rate_remaining=args.rate_remaining,
        context_remaining=args.context_remaining,
        five_hour_minutes=args.five_hour_minutes,
        default_thread_id=args.thread_id,
        output_mode=args.output_mode,
        skill_path=args.skill_path,
        state=state,
    )
    for line_number, line in enumerate(sys.stdin, start=1):
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message is not an object")
            for output in watcher.process(message):
                print(json.dumps(output, ensure_ascii=False), flush=True)
            state.save(args.state_file)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            print(f"warning: line {line_number}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
