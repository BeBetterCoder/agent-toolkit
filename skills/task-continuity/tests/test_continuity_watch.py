from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("continuity_watch", SKILL_ROOT / "scripts/continuity_watch.py")
assert spec and spec.loader
watch = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = watch
spec.loader.exec_module(watch)


class WatcherTests(unittest.TestCase):
    def watcher(self, output_mode="action"):
        return watch.ContinuityWatcher(
            rate_remaining=10,
            context_remaining=15,
            five_hour_minutes=300,
            default_thread_id="thr_test",
            output_mode=output_mode,
            skill_path="/skills/task-continuity/SKILL.md",
        )

    def test_rate_threshold_and_deduplication(self):
        watcher = self.watcher()
        message = {
            "method": "account/rateLimits/updated",
            "params": {
                "rateLimits": {
                    "limitId": "codex",
                    "primary": {"usedPercent": 91, "windowDurationMins": 300, "resetsAt": 123},
                }
            },
        }
        first = watcher.process(message)
        second = watcher.process(message)
        self.assertEqual(first[0]["reasons"], ["rate-limit-low"])
        self.assertEqual(first[0]["signals"][0]["remainingPercent"], 9)
        self.assertEqual(second, [])

    def test_sparse_rate_update_uses_cached_window_metadata(self):
        watcher = self.watcher()
        watcher.process(
            {
                "method": "account/rateLimits/updated",
                "params": {
                    "rateLimits": {
                        "limitId": "codex",
                        "primary": {"usedPercent": 50, "windowDurationMins": 300, "resetsAt": 456},
                    }
                },
            }
        )
        result = watcher.process(
            {
                "method": "account/rateLimits/updated",
                "params": {"rateLimits": {"limitId": "codex", "primary": {"usedPercent": 92}}},
            }
        )
        self.assertEqual(result[0]["reasons"], ["rate-limit-low"])

    def test_context_waits_for_active_turn_and_rearms(self):
        watcher = self.watcher(output_mode="turn-start")
        watcher.process({"method": "turn/started", "params": {"threadId": "thr_test", "turn": {"id": "turn_1"}}})
        low = {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": "thr_test",
                "turnId": "turn_1",
                "tokenUsage": {
                    "modelContextWindow": 1000,
                    "last": {"totalTokens": 860},
                    "total": {"totalTokens": 2000},
                },
            },
        }
        self.assertEqual(watcher.process(low), [])
        completed = watcher.process(
            {"method": "turn/completed", "params": {"threadId": "thr_test", "turn": {"id": "turn_1", "status": "completed"}}}
        )
        self.assertEqual(completed[0]["method"], "turn/start")
        self.assertIn("context-low", completed[0]["params"]["input"][0]["text"])
        self.assertEqual(watcher.process(low), [])

        high = {
            **low,
            "params": {
                **low["params"],
                "tokenUsage": {
                    "modelContextWindow": 1000,
                    "last": {"totalTokens": 100},
                    "total": {"totalTokens": 2100},
                },
            },
        }
        self.assertEqual(watcher.process(high), [])
        self.assertEqual(len(watcher.process(low)), 1)


if __name__ == "__main__":
    unittest.main()
