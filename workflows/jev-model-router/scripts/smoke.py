"""Run one harmless turn through the configured routing proxy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import selectors
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    process = subprocess.Popen(
        [sys.executable, "-m", "jev_model_router.proxy", "--config", str(args.config)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    assert process.stdin is not None and process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    next_id = 0
    deadline = time.monotonic() + args.timeout

    def send(method: str, params: dict | None = None, *, request: bool = True) -> int | None:
        nonlocal next_id
        message = {"method": method}
        if params is not None:
            message["params"] = params
        if request:
            next_id += 1
            message["id"] = next_id
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        return message.get("id")

    def receive() -> dict:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not selector.select(remaining):
            raise TimeoutError("App Server response timed out")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("App Server closed its output")
        return json.loads(line)

    def response(request_id: int) -> dict:
        while True:
            message = receive()
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"App Server error: {message['error']}")
                return message["result"]

    try:
        response(send("initialize", {"clientInfo": {"name": "jev-model-router-smoke", "version": "0.1.0"}}))
        send("initialized", request=False)
        started = response(send("thread/start", {
            "cwd": str(args.cwd.resolve()),
            "sandbox": "read-only",
            "approvalPolicy": "never",
        }))
        thread_id = started["thread"]["id"]
        response(send("turn/start", {
            "threadId": thread_id,
            "input": [{"type": "text", "text": "Reply with exactly ROUTER_OK."}],
        }))
        while True:
            message = receive()
            if message.get("method") == "turn/completed":
                params = message.get("params", {})
                if params.get("threadId") == thread_id:
                    status = params.get("turn", {}).get("status")
                    print(json.dumps({"thread_id": thread_id, "turn_status": status}))
                    return 0 if status == "completed" else 1
    finally:
        process.terminate()
        process.communicate(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
