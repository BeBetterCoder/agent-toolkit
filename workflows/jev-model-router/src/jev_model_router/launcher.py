"""Start the routed App Server and an interactive Codex TUI in the current repo."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .config import load_config


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config.toml"


def codex_arguments(socket_path: Path, workspace: Path, forwarded: list[str]) -> list[str]:
    args = forwarded[1:] if forwarded[:1] == ["--"] else forwarded
    if "-C" not in args and "--cd" not in args:
        args = ["-C", str(workspace), *args]
    return ["codex", "--remote", f"unix://{socket_path}", *args]


def shared_app_server_socket() -> Path:
    check = subprocess.run(
        ["codex", "app-server", "daemon", "version"],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(check.stdout)
    if info.get("status") != "running":
        subprocess.run(["codex", "app-server", "daemon", "start"], check=True)
        check = subprocess.run(
            ["codex", "app-server", "daemon", "version"],
            capture_output=True, text=True, check=True,
        )
        info = json.loads(check.stdout)
    socket_path = info.get("socketPath")
    if not isinstance(socket_path, str) or not Path(socket_path).exists():
        raise RuntimeError("shared Codex App Server socket is unavailable")
    return Path(socket_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, add_help=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args, forwarded = parser.parse_known_args()
    config_path = args.config.resolve()
    config = load_config(config_path)
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("Jev key unavailable; routing will fall back to BALANCED.", file=sys.stderr)
    print(f"Jev routing: {config['mode']} | workspace: {Path.cwd()}", file=sys.stderr)
    upstream_socket = shared_app_server_socket()

    with tempfile.TemporaryDirectory(prefix="jev-codex-") as temp_dir:
        socket_path = Path(temp_dir) / "router.sock"
        proxy = subprocess.Popen(
            [sys.executable, "-m", "jev_model_router.ws_proxy", "--config", str(config_path), "--socket", str(socket_path), "--upstream-socket", str(upstream_socket)],
            stdout=subprocess.DEVNULL,
            stderr=sys.stderr,
        )
        try:
            for _ in range(50):
                if proxy.poll() is not None:
                    raise RuntimeError("router exited during startup")
                if socket_path.exists():
                    break
                time.sleep(0.1)
            else:
                raise TimeoutError("router startup timed out")
            return subprocess.call(codex_arguments(socket_path, Path.cwd(), forwarded))
        finally:
            proxy.terminate()
            proxy.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
