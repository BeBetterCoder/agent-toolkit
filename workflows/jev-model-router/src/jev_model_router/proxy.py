"""Transparent JSONL proxy in front of `codex app-server --stdio`."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

from .config import load_config
from .context import task_from_turn
from .jev_client import JevClient
from .router import Router
from .telemetry import Telemetry


class RoutingProxy:
    def __init__(
        self,
        config: dict[str, Any],
        router: Router,
        telemetry: Telemetry,
        config_hash: str,
        *,
        route_only_user_trigger: bool = False,
    ) -> None:
        self.config = config
        self.router = router
        self.telemetry = telemetry
        self.config_hash = config_hash
        self.route_only_user_trigger = route_only_user_trigger
        self.lock = threading.Lock()
        self.active_threads: set[str] = set()
        self.failed_threads: set[str] = set()
        self.current: dict[str, dict[str, Any]] = {}
        self.usage: dict[str, dict[str, Any]] = {}

    def write_event(self, record: dict[str, Any]) -> None:
        try:
            self.telemetry.write(record)
        except OSError as exc:
            print(f"router telemetry unavailable: {type(exc).__name__}", file=sys.stderr)

    def client_message(self, message: dict[str, Any]) -> dict[str, Any]:
        if message.get("method") != "turn/start":
            return message
        params = message.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("threadId"), str):
            return message
        if self.route_only_user_trigger and params.get("turnTrigger") != "user":
            return message
        thread_id = params["threadId"]
        with self.lock:
            # A turn/start can steer an active turn. Routing only applies to new turns.
            if thread_id in self.active_threads:
                return message
            previous_failed = thread_id in self.failed_threads
        task = task_from_turn(params)
        route, routing_ms = self.router.route(
            task,
            cwd=params.get("cwd"),
            previous_failed=previous_failed,
        )
        if self.config["mode"] == "route":
            params = {**params, "model": route.model, "effort": route.effort}
            collaboration = params.get("collaborationMode")
            if isinstance(collaboration, dict) and isinstance(collaboration.get("settings"), dict):
                settings = {
                    **collaboration["settings"],
                    "model": route.model,
                    "reasoning_effort": route.effort,
                }
                params["collaborationMode"] = {**collaboration, "settings": settings}
            message = {**message, "params": params}
        record = {
            "event": "routing",
            "thread_id": thread_id,
            "task": task,
            "tier": route.tier,
            "confidence": route.confidence,
            "probabilities": route.probabilities,
            "selected_model": route.model,
            "reasoning_effort": route.effort,
            "effective_model": route.model if self.config["mode"] == "route" else params.get("model"),
            "effective_effort": route.effort if self.config["mode"] == "route" else params.get("effort"),
            "routing_latency_ms": routing_ms,
            "fallback_reason": route.fallback_reason,
            "mode": self.config["mode"],
            "turn_trigger": params.get("turnTrigger"),
            "config_sha256": self.config_hash,
            "timestamp": time.time(),
        }
        with self.lock:
            self.current[thread_id] = {"started": time.perf_counter(), **record}
        self.write_event(record)
        return message

    def server_message(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(params, dict):
            return
        thread_id = params.get("threadId")
        if not isinstance(thread_id, str):
            return
        with self.lock:
            if method == "turn/started":
                self.active_threads.add(thread_id)
            elif method == "thread/tokenUsage/updated":
                usage = params.get("tokenUsage")
                if isinstance(usage, dict):
                    self.usage[thread_id] = usage.get("last", {})
            elif method == "turn/completed":
                self.active_threads.discard(thread_id)
                turn = params.get("turn", {})
                status = turn.get("status") if isinstance(turn, dict) else None
                if status == "completed":
                    self.failed_threads.discard(thread_id)
                else:
                    self.failed_threads.add(thread_id)
                record = self.current.pop(thread_id, None)
                if record:
                    self.write_event({
                        "event": "codex_completed",
                        "thread_id": thread_id,
                        "tier": record["tier"],
                        "codex_latency_ms": round((time.perf_counter() - record["started"]) * 1000, 1),
                        "token_usage": self.usage.pop(thread_id, None),
                        "task_result": status,
                        "turn_id": turn.get("id") if isinstance(turn, dict) else None,
                        "config_sha256": self.config_hash,
                        "timestamp": time.time(),
                    })


def serve(config_path: Path, codex_command: list[str]) -> int:
    config = load_config(config_path)
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()[:16]
    router = Router(
        JevClient(config["jev_timeout_seconds"]),
        config["tiers"],
        config["confidence_threshold"],
    )
    proxy = RoutingProxy(config, router, Telemetry(config["telemetry_path"]), config_hash)
    command = codex_command or ["codex", "app-server", "--stdio"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1)
    assert process.stdin is not None and process.stdout is not None
    output_lock = threading.Lock()

    def from_server() -> None:
        for line in process.stdout:
            try:
                message = json.loads(line)
                if isinstance(message, dict):
                    proxy.server_message(message)
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                print(f"router telemetry warning: {type(exc).__name__}", file=sys.stderr)
            with output_lock:
                sys.stdout.write(line)
                sys.stdout.flush()

    server_thread = threading.Thread(target=from_server, daemon=True)
    server_thread.start()
    try:
        for line in sys.stdin:
            try:
                message = json.loads(line)
                if isinstance(message, dict):
                    line = json.dumps(proxy.client_message(message), ensure_ascii=False, separators=(",", ":")) + "\n"
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                print(f"router input warning: {type(exc).__name__}", file=sys.stderr)
            process.stdin.write(line)
            process.stdin.flush()
    except BrokenPipeError:
        pass
    finally:
        process.stdin.close()
    exit_code = process.wait()
    server_thread.join(timeout=2)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--codex", nargs=argparse.REMAINDER, help="alternate App Server command")
    args = parser.parse_args()
    try:
        return serve(args.config, args.codex or [])
    except (OSError, ValueError) as exc:
        print(f"router startup failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
