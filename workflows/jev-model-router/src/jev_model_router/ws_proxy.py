"""Local WebSocket endpoint for `codex --remote`, backed by routed App Server stdio."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from websockets.asyncio.client import unix_connect
from websockets.asyncio.server import unix_serve

from .config import load_config
from .jev_client import JevClient
from .proxy import RoutingProxy
from .router import Router
from .telemetry import Telemetry


async def client_session(
    websocket: Any,
    config: dict[str, Any],
    config_hash: str,
    upstream_socket: Path,
) -> None:
    router = Router(
        JevClient(config["jev_timeout_seconds"]),
        config["tiers"],
        config["confidence_threshold"],
    )
    routing = RoutingProxy(
        config,
        router,
        Telemetry(config["telemetry_path"]),
        config_hash,
        route_only_user_trigger=True,
    )
    async with unix_connect(str(upstream_socket), max_size=16 * 1024 * 1024) as codex:
        async def from_codex() -> None:
            async for frame in codex:
                try:
                    message = json.loads(frame)
                    if isinstance(message, dict):
                        routing.server_message(message)
                except (json.JSONDecodeError, OSError, ValueError) as exc:
                    print(f"router server message warning: {type(exc).__name__}", file=sys.stderr)
                await websocket.send(frame)

        async def from_client() -> None:
            async for frame in websocket:
                if not isinstance(frame, str):
                    continue
                try:
                    message = json.loads(frame)
                    if isinstance(message, dict):
                        message = await asyncio.to_thread(routing.client_message, message)
                        frame = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
                except (json.JSONDecodeError, OSError, ValueError) as exc:
                    print(f"router client message warning: {type(exc).__name__}", file=sys.stderr)
                await codex.send(frame)

        upstream = asyncio.create_task(from_codex())
        downstream = asyncio.create_task(from_client())
        done, pending = await asyncio.wait(
            (upstream, downstream), return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            task.result()
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def run(config_path: Path, socket_path: Path, upstream_socket: Path) -> None:
    config = load_config(config_path)
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()[:16]
    async with unix_serve(
        lambda connection: client_session(connection, config, config_hash, upstream_socket),
        path=str(socket_path), max_size=16 * 1024 * 1024,
    ):
        socket_path.chmod(0o600)
        print(f"JEV_ROUTER_READY={socket_path}", file=sys.stderr, flush=True)
        await asyncio.Future()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--upstream-socket", type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.config, args.socket, args.upstream_socket))
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        print(f"router startup failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
