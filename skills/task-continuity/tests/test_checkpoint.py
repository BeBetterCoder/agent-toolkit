from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checkpoint = load_module("checkpoint", SKILL_ROOT / "scripts/checkpoint.py")


def draft() -> dict:
    return {
        "status": "active",
        "task": {
            "objective": "Finish the migration",
            "constraints": ["Do not repeat remote mutations"],
            "acceptance_criteria": ["Tests pass"],
        },
        "progress": {
            "current_state": "Implementation is ready for verification",
            "completed": ["Created files"],
            "remaining": ["Run tests"],
            "do_not_repeat": ["Repository creation"],
        },
        "decisions": [
            {
                "decision": "Use JSON as the source of truth",
                "rationale": "It is machine-readable",
                "alternatives_rejected": ["Markdown-only state"],
            }
        ],
        "verification": {"not_run": ["Unit tests"]},
        "runtime": {"pending_approvals": ["Push requires user authorization"]},
        "resume": {
            "next_action": "Run unit tests",
            "files_to_read_first": ["README.md"],
            "resume_prompt": "Continue from the saved next action.",
        },
    }


class CheckpointTests(unittest.TestCase):
    def test_normalize_rejects_secret(self):
        value = draft()
        value["progress"]["current_state"] = "token sk-abcdefghijklmnopqrstuvwxyz"
        with self.assertRaises(checkpoint.CheckpointError):
            checkpoint.normalize_draft(value)

    def test_save_validate_and_detect_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            (root / "tracked.txt").write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, stdout=subprocess.DEVNULL)
            (root / "tracked.txt").write_text("changed before checkpoint\n", encoding="utf-8")
            input_path = root / "draft.json"
            input_path.write_text(json.dumps(draft()), encoding="utf-8")

            result = subprocess.run(
                ["python3", str(SKILL_ROOT / "scripts/checkpoint.py"), "save", "--root", str(root), "--input", str(input_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            saved = json.loads(result.stdout)
            latest_json, latest_md = Path(saved["json"]), Path(saved["markdown"])
            self.assertTrue(latest_json.exists())
            self.assertIn("Finish the migration", latest_md.read_text(encoding="utf-8"))
            workspace = json.loads(latest_json.read_text(encoding="utf-8"))["workspace"]
            self.assertIn({"code": " M", "path": "tracked.txt"}, workspace["changes"])

            validate = subprocess.run(
                ["python3", str(SKILL_ROOT / "scripts/checkpoint.py"), "validate", "--input", str(latest_json)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validate.stdout.strip(), "valid")

            unchanged = subprocess.run(
                ["python3", str(SKILL_ROOT / "scripts/checkpoint.py"), "status", "--root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertFalse(json.loads(unchanged.stdout)["workspace_drift"])

            (root / "tracked.txt").write_text("two\n", encoding="utf-8")
            status = subprocess.run(
                ["python3", str(SKILL_ROOT / "scripts/checkpoint.py"), "status", "--root", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(json.loads(status.stdout)["workspace_drift"])


if __name__ == "__main__":
    unittest.main()
