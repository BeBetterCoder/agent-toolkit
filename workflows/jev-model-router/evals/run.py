"""Run the labeled routing cases against the configured Jev classifier."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys
import time

from jev_model_router.config import load_config
from jev_model_router.context import routing_state, safe_task
from jev_model_router.jev_client import JevClient
from jev_model_router.policy import TIERS, choose_route


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.toml")
    parser.add_argument("--output", type=Path, help="write the full JSON report to this path")
    args = parser.parse_args()

    config = load_config(args.config)
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        parser.error("cases must be a nonempty JSON array")
    if any(not isinstance(case, dict) or case.get("expected") not in TIERS or not isinstance(case.get("prompt"), str) for case in cases):
        parser.error("every case needs a prompt and expected tier")

    client = JevClient(config["jev_timeout_seconds"])
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            answer = client.judge(routing_state(safe_task(case["prompt"]), cwd=str(PROJECT_ROOT), previous_failed=False))
        except Exception as exc:
            print(f"{case.get('id')}: Jev call failed ({type(exc).__name__})", file=sys.stderr)
            return 2
        route = choose_route(answer, config["tiers"], config["confidence_threshold"])
        result = {
            "id": case.get("id"),
            "prompt": case["prompt"],
            "expected": case["expected"],
            "jev_choice": answer.get("choice") if isinstance(answer, dict) else None,
            "confidence": route.confidence,
            "probabilities": route.probabilities,
            "effective_tier": route.tier,
            "fallback_reason": route.fallback_reason,
            "selected_model": route.model,
            "reasoning_effort": route.effort,
            "routing_latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        results.append(result)
        print(f"{result['id']}: expected={result['expected']} jev={result['jev_choice']} effective={result['effective_tier']} confidence={result['confidence']} fallback={result['fallback_reason']}", flush=True)

    total = len(results)
    summary = {
        "cases": total,
        "choice_accuracy": sum(result["jev_choice"] == result["expected"] for result in results) / total,
        "effective_accuracy": sum(result["effective_tier"] == result["expected"] for result in results) / total,
        "fallbacks": dict(Counter(result["fallback_reason"] for result in results if result["fallback_reason"])),
        "median_routing_latency_ms": median(result["routing_latency_ms"] for result in results),
        "expected_tiers": dict(Counter(result["expected"] for result in results)),
        "effective_tiers": dict(Counter(result["effective_tier"] for result in results)),
    }
    report = {"config": {"confidence_threshold": config["confidence_threshold"], "tiers": config["tiers"]}, "summary": summary, "results": results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
