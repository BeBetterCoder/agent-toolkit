#!/usr/bin/env python3
"""Validate, enrich, save, render, and inspect task-continuity checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
HANDOFF_DIR = Path(".codex/handoffs")
VALID_STATUSES = {"active", "paused", "blocked", "complete"}
MAX_INPUT_BYTES = 128 * 1024
MAX_LIST_ITEMS = 100
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
)


class CheckpointError(ValueError):
    pass


def run_git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.rstrip("\n")


def project_root(start: Path) -> Path:
    start = start.resolve()
    resolved = run_git(start, "rev-parse", "--show-toplevel")
    return Path(resolved).resolve() if resolved else start


def as_string(value: Any, path: str, *, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise CheckpointError(f"{path} must be a string")
    value = value.strip()
    if required and not value:
        raise CheckpointError(f"{path} must not be empty")
    if len(value) > 12_000:
        raise CheckpointError(f"{path} is too long")
    return value


def as_string_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CheckpointError(f"{path} must be an array")
    if len(value) > MAX_LIST_ITEMS:
        raise CheckpointError(f"{path} has more than {MAX_LIST_ITEMS} items")
    return [as_string(item, f"{path}[{i}]", required=True) for i, item in enumerate(value)]


def as_object(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CheckpointError(f"{path} must be an object")
    return value


def reject_unknown(obj: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise CheckpointError(f"{path} contains unsupported fields: {', '.join(unknown)}")


def scan_secrets(value: Any, path: str = "checkpoint") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            scan_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_secrets(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            raise CheckpointError(f"possible secret detected at {path}")


def normalize_draft(raw: dict[str, Any]) -> dict[str, Any]:
    reject_unknown(raw, {"status", "task", "progress", "decisions", "verification", "runtime", "resume"}, "checkpoint")
    status = as_string(raw.get("status", "active"), "status", required=True)
    if status not in VALID_STATUSES:
        raise CheckpointError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")

    task = as_object(raw.get("task"), "task")
    reject_unknown(task, {"objective", "user_intent", "constraints", "non_goals", "acceptance_criteria"}, "task")
    progress = as_object(raw.get("progress"), "progress")
    reject_unknown(progress, {"current_state", "completed", "in_progress", "remaining", "do_not_repeat"}, "progress")
    verification = as_object(raw.get("verification"), "verification")
    reject_unknown(verification, {"passed", "failed", "not_run"}, "verification")
    runtime = as_object(raw.get("runtime"), "runtime")
    reject_unknown(runtime, {"background_processes", "external_changes", "pending_approvals", "blockers"}, "runtime")
    resume = as_object(raw.get("resume"), "resume")
    reject_unknown(resume, {"next_action", "files_to_read_first", "commands_to_run_first", "open_questions", "resume_prompt"}, "resume")

    decisions_raw = raw.get("decisions", [])
    if not isinstance(decisions_raw, list) or len(decisions_raw) > MAX_LIST_ITEMS:
        raise CheckpointError("decisions must be a bounded array")
    decisions = []
    for index, item in enumerate(decisions_raw):
        item = as_object(item, f"decisions[{index}]")
        reject_unknown(item, {"decision", "rationale", "alternatives_rejected"}, f"decisions[{index}]")
        decisions.append(
            {
                "decision": as_string(item.get("decision"), f"decisions[{index}].decision", required=True),
                "rationale": as_string(item.get("rationale"), f"decisions[{index}].rationale", required=True),
                "alternatives_rejected": as_string_list(item.get("alternatives_rejected"), f"decisions[{index}].alternatives_rejected"),
            }
        )

    normalized = {
        "status": status,
        "task": {
            "objective": as_string(task.get("objective"), "task.objective", required=True),
            "user_intent": as_string_list(task.get("user_intent"), "task.user_intent"),
            "constraints": as_string_list(task.get("constraints"), "task.constraints"),
            "non_goals": as_string_list(task.get("non_goals"), "task.non_goals"),
            "acceptance_criteria": as_string_list(task.get("acceptance_criteria"), "task.acceptance_criteria"),
        },
        "progress": {
            "current_state": as_string(progress.get("current_state"), "progress.current_state", required=True),
            "completed": as_string_list(progress.get("completed"), "progress.completed"),
            "in_progress": as_string_list(progress.get("in_progress"), "progress.in_progress"),
            "remaining": as_string_list(progress.get("remaining"), "progress.remaining"),
            "do_not_repeat": as_string_list(progress.get("do_not_repeat"), "progress.do_not_repeat"),
        },
        "decisions": decisions,
        "verification": {key: as_string_list(verification.get(key), f"verification.{key}") for key in ("passed", "failed", "not_run")},
        "runtime": {key: as_string_list(runtime.get(key), f"runtime.{key}") for key in ("background_processes", "external_changes", "pending_approvals", "blockers")},
        "resume": {
            "next_action": as_string(resume.get("next_action"), "resume.next_action", required=True),
            "files_to_read_first": as_string_list(resume.get("files_to_read_first"), "resume.files_to_read_first"),
            "commands_to_run_first": as_string_list(resume.get("commands_to_run_first"), "resume.commands_to_run_first"),
            "open_questions": as_string_list(resume.get("open_questions"), "resume.open_questions"),
            "resume_prompt": as_string(resume.get("resume_prompt"), "resume.resume_prompt"),
        },
    }
    scan_secrets(normalized)
    return normalized


def collect_workspace(root: Path) -> dict[str, Any]:
    head = run_git(root, "rev-parse", "HEAD")
    if head is None:
        return {"root_name": root.name, "is_git_repository": False}
    status_text = run_git(root, "status", "--short", "--untracked-files=all") or ""
    changes = [
        {"code": line[:2], "path": line[3:] if len(line) > 3 else ""}
        for line in status_text.splitlines()
        if line and not (line[3:] if len(line) > 3 else "").startswith(".codex/handoffs/")
    ]
    fingerprint = hashlib.sha256()
    fingerprint.update(head.encode("utf-8"))
    try:
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--binary", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ).stdout
        fingerprint.update(diff)
        untracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ).stdout.split(b"\0")
        for raw_path in sorted(path for path in untracked if path):
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            if relative.startswith(".codex/handoffs/"):
                continue
            fingerprint.update(raw_path)
            path = root / relative
            if path.is_symlink():
                fingerprint.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
            elif path.is_file():
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        fingerprint.update(chunk)
    except (OSError, subprocess.CalledProcessError):
        fingerprint.update(status_text.encode("utf-8"))
    return {
        "root_name": root.name,
        "is_git_repository": True,
        "branch": run_git(root, "branch", "--show-current") or None,
        "head": head,
        "dirty": bool(changes),
        "changes": changes,
        "worktree_fingerprint": fingerprint.hexdigest(),
    }


def render_markdown(doc: dict[str, Any]) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- None recorded"

    task, progress = doc["task"], doc["progress"]
    verification, runtime, resume = doc["verification"], doc["runtime"], doc["resume"]
    workspace = doc["workspace"]
    decisions = []
    for item in doc["decisions"]:
        text = f"- **{item['decision']}** — {item['rationale']}"
        if item["alternatives_rejected"]:
            text += "; rejected: " + "; ".join(item["alternatives_rejected"])
        decisions.append(text)

    workspace_lines = [f"- Project: `{workspace['root_name']}`"]
    if workspace.get("is_git_repository"):
        workspace_lines.extend(
            [
                f"- Branch: `{workspace.get('branch') or '(detached)'}`",
                f"- HEAD: `{workspace.get('head')}`",
                f"- Dirty: `{str(workspace.get('dirty', False)).lower()}`",
            ]
        )
        workspace_lines.extend(f"- Change `{item['code']}`: `{item['path']}`" for item in workspace.get("changes", []))

    sections = [
        "# Task Handoff", "",
        f"- Status: `{doc['status']}`",
        f"- Checkpoint: `{doc['checkpoint_id']}`",
        f"- Created: `{doc['created_at']}`",
        f"- Trigger: `{doc['trigger']['reason']}`", "",
        "## Objective", "", task["objective"], "",
        "## Current state", "", progress["current_state"], "",
        "## Constraints", "", bullets(task["constraints"]), "",
        "## Completed", "", bullets(progress["completed"]), "",
        "## In progress", "", bullets(progress["in_progress"]), "",
        "## Remaining", "", bullets(progress["remaining"]), "",
        "## Do not repeat", "", bullets(progress["do_not_repeat"]), "",
        "## Decisions", "", "\n".join(decisions) if decisions else "- None recorded", "",
        "## Workspace", "", "\n".join(workspace_lines), "",
        "## Verification", "", "### Passed", "", bullets(verification["passed"]), "",
        "### Failed", "", bullets(verification["failed"]), "", "### Not run", "", bullets(verification["not_run"]), "",
        "## External state and blockers", "", "### External changes", "", bullets(runtime["external_changes"]), "",
        "### Pending approvals", "", bullets(runtime["pending_approvals"]), "", "### Blockers", "", bullets(runtime["blockers"]), "",
        "## Resume", "", f"**Next action:** {resume['next_action']}", "",
        "### Read first", "", bullets(resume["files_to_read_first"]), "",
        "### Commands to run first", "", bullets(resume["commands_to_run_first"]), "",
        "### Open questions", "", bullets(resume["open_questions"]),
    ]
    if resume["resume_prompt"]:
        sections.extend(["", "### Ready-to-use prompt", "", resume["resume_prompt"]])
    return "\n".join(sections).rstrip() + "\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_json(path: str) -> dict[str, Any]:
    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1) if path == "-" else Path(path).read_bytes()
    if len(data) > MAX_INPUT_BYTES:
        raise CheckpointError(f"checkpoint input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        value = json.loads(data)
    except json.JSONDecodeError as exc:
        raise CheckpointError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CheckpointError("checkpoint must be a JSON object")
    return value


def ignore_warning(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    ignored = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", str(HANDOFF_DIR / "latest.json")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    return None if ignored else ".codex/handoffs/ is not ignored; review before committing private task context"


def save_checkpoint(args: argparse.Namespace) -> int:
    root = project_root(Path(args.root))
    normalized = normalize_draft(load_json(args.input))
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    checkpoint_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    doc = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": checkpoint_id,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "trigger": {"reason": args.reason},
        **normalized,
        "workspace": collect_workspace(root),
    }
    scan_secrets(doc)
    handoff_dir, history_dir = root / HANDOFF_DIR, root / HANDOFF_DIR / "history"
    json_text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    markdown = render_markdown(doc)
    for path, content in (
        (handoff_dir / "latest.json", json_text),
        (handoff_dir / "latest.md", markdown),
        (history_dir / f"{checkpoint_id}.json", json_text),
        (history_dir / f"{checkpoint_id}.md", markdown),
    ):
        atomic_write(path, content)
    old_files = sorted(history_dir.glob("*.json"), key=lambda path: path.name, reverse=True)[max(args.history_limit, 0):]
    for old_json in old_files:
        old_json.unlink(missing_ok=True)
        old_json.with_suffix(".md").unlink(missing_ok=True)
    print(json.dumps({"checkpoint_id": checkpoint_id, "json": str(handoff_dir / "latest.json"), "markdown": str(handoff_dir / "latest.md"), "warning": ignore_warning(root)}, ensure_ascii=False, indent=2))
    return 0


def validate_checkpoint(args: argparse.Namespace) -> int:
    raw = load_json(args.input)
    if "schema_version" in raw:
        required = {"schema_version", "checkpoint_id", "created_at", "trigger", "workspace"}
        missing = sorted(required - set(raw))
        if missing:
            raise CheckpointError(f"saved checkpoint is missing: {', '.join(missing)}")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise CheckpointError(f"unsupported schema_version: {raw['schema_version']}")
        scan_secrets(raw)
        raw = {key: raw[key] for key in ("status", "task", "progress", "decisions", "verification", "runtime", "resume")}
    normalize_draft(raw)
    print("valid")
    return 0


def render_checkpoint(args: argparse.Namespace) -> int:
    raw = load_json(args.input)
    if "schema_version" not in raw:
        raise CheckpointError("render requires a saved checkpoint, not a draft")
    markdown = render_markdown(raw)
    atomic_write(Path(args.output), markdown) if args.output else sys.stdout.write(markdown)
    return 0


def checkpoint_status(args: argparse.Namespace) -> int:
    root = project_root(Path(args.root))
    latest = root / HANDOFF_DIR / "latest.json"
    if not latest.exists():
        print(json.dumps({"exists": False, "path": str(latest)}, indent=2))
        return 1
    raw = load_json(str(latest))
    saved, current = raw.get("workspace", {}), collect_workspace(root)
    print(json.dumps({"exists": True, "checkpoint_id": raw.get("checkpoint_id"), "status": raw.get("status"), "json": str(latest), "markdown": str(latest.with_suffix(".md")), "workspace_drift": saved != current, "saved_workspace": saved, "current_workspace": current, "warning": ignore_warning(root)}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    save = commands.add_parser("save", help="validate and atomically save a checkpoint draft")
    save.add_argument("--input", required=True, help="draft JSON path, or - for stdin")
    save.add_argument("--root", default=".")
    save.add_argument("--reason", default="manual")
    save.add_argument("--history-limit", type=int, default=5)
    save.set_defaults(func=save_checkpoint)
    validate = commands.add_parser("validate", help="validate a draft or saved checkpoint")
    validate.add_argument("--input", required=True)
    validate.set_defaults(func=validate_checkpoint)
    render = commands.add_parser("render", help="render a saved checkpoint as Markdown")
    render.add_argument("--input", required=True)
    render.add_argument("--output")
    render.set_defaults(func=render_checkpoint)
    status = commands.add_parser("status", help="inspect the latest checkpoint and workspace drift")
    status.add_argument("--root", default=".")
    status.set_defaults(func=checkpoint_status)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except (CheckpointError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
