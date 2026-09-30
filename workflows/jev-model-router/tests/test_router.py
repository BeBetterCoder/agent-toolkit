from __future__ import annotations

import copy
import json

from jev_model_router.config import load_config
from jev_model_router.context import safe_task
from jev_model_router.launcher import codex_arguments
from jev_model_router.policy import choose_route
from jev_model_router.proxy import RoutingProxy
from jev_model_router.router import Router


TIERS = {
    "FAST": {"model": "fast-model", "effort": "low"},
    "BALANCED": {"model": "balanced-model", "effort": "medium"},
    "DEEP": {"model": "deep-model", "effort": "high"},
}


class FakeJev:
    def __init__(self, answer=None, error=None):
        self.answer = answer
        self.error = error
        self.states = []

    def judge(self, state):
        self.states.append(state)
        if self.error:
            raise self.error
        return self.answer


class FakeTelemetry:
    def __init__(self):
        self.events = []

    def write(self, event):
        self.events.append(event)


def answer(choice="DEEP", confidence=0.93):
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": {"FAST": 0.02, "BALANCED": 0.05, "DEEP": 0.93},
    }


def turn(text="Find the race condition"):
    return {
        "id": 7,
        "method": "turn/start",
        "params": {"threadId": "thread-1", "input": [{"type": "text", "text": text}]},
    }


def proxy(mode="route", jev=None):
    telemetry = FakeTelemetry()
    jev = jev or FakeJev(answer())
    instance = RoutingProxy(
        {"mode": mode}, Router(jev, TIERS, 0.8), telemetry, "config-hash"
    )
    return instance, telemetry, jev


def test_high_confidence_changes_only_turn_model_and_effort():
    instance, telemetry, jev = proxy()
    request = turn()
    routed = instance.client_message(copy.deepcopy(request))
    assert routed["params"]["model"] == "deep-model"
    assert routed["params"]["effort"] == "high"
    assert request["params"] == {"threadId": "thread-1", "input": request["params"]["input"]}
    assert jev.states[0]["task"] == "Find the race condition"
    assert telemetry.events[0]["tier"] == "DEEP"


def test_shadow_observes_without_changing_request():
    instance, telemetry, _ = proxy(mode="shadow")
    request = turn()
    assert instance.client_message(copy.deepcopy(request)) == request
    assert telemetry.events[0]["selected_model"] == "deep-model"
    assert telemetry.events[0]["effective_model"] is None


def test_low_confidence_or_error_falls_back_to_balanced():
    assert choose_route(answer(confidence=0.6), TIERS, 0.8).tier == "BALANCED"
    assert choose_route(answer(confidence=0.6), TIERS, 0.8).fallback_reason == "low_confidence"
    instance, _, _ = proxy(jev=FakeJev(error=TimeoutError()))
    assert instance.client_message(turn())["params"]["model"] == "balanced-model"


def test_invalid_response_falls_back_to_balanced():
    invalid = answer()
    del invalid["probabilities"]
    assert choose_route(invalid, TIERS, 0.8).fallback_reason == "invalid_response"


def test_steering_does_not_route_and_next_turn_routes_again():
    instance, telemetry, jev = proxy()
    instance.client_message(turn())
    instance.server_message({"method": "turn/started", "params": {"threadId": "thread-1"}})
    steer = turn("Actually inspect the lock")
    assert instance.client_message(steer) == steer
    instance.server_message({"method": "turn/completed", "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "failed"}}})
    instance.client_message(turn("Try again"))
    assert len(jev.states) == 2
    assert jev.states[-1]["previous_turn_failed"] is True
    assert [x["event"] for x in telemetry.events] == ["routing", "codex_completed", "routing"]


def test_redacts_common_credentials_before_external_call_or_logging():
    instance, telemetry, jev = proxy()
    instance.client_message(turn("Investigate api_key=abc123 and sk-ABCDEFGHIJKLMNOP"))
    assert "abc123" not in json.dumps(jev.states)
    assert "sk-ABCDEFGHIJKLMNOP" not in json.dumps(telemetry.events)
    assert "[REDACTED]" in safe_task("password: hidden")


def test_config_example_is_valid():
    from pathlib import Path

    config = load_config(Path(__file__).resolve().parents[1] / "config.example.toml")
    assert config["mode"] == "shadow"
    assert set(config["tiers"]) == set(TIERS)


def test_telemetry_failure_does_not_block_routing():
    class FailingTelemetry:
        def write(self, event):
            raise OSError("read-only log path")

    instance = RoutingProxy(
        {"mode": "route"}, Router(FakeJev(answer()), TIERS, 0.8), FailingTelemetry(), "hash"
    )
    assert instance.client_message(turn())["params"]["model"] == "deep-model"


def test_launcher_targets_current_workspace_unless_overridden(tmp_path):
    workspace = tmp_path / "repository"
    socket_path = tmp_path / "router.sock"
    assert codex_arguments(socket_path, workspace, ["--no-alt-screen"])[3:5] == ["-C", str(workspace)]
    assert codex_arguments(socket_path, workspace, ["-C", "/another/repo"])[3:] == ["-C", "/another/repo"]


def test_tui_proxy_routes_only_user_turns():
    jev = FakeJev(answer())
    telemetry = FakeTelemetry()
    instance = RoutingProxy(
        {"mode": "route"},
        Router(jev, TIERS, 0.8),
        telemetry,
        "hash",
        route_only_user_trigger=True,
    )
    automatic = turn("Generate a concise, single-line task title")
    assert instance.client_message(automatic) == automatic
    user_turn = turn("Fix the bug")
    user_turn["params"]["turnTrigger"] = "user"
    assert instance.client_message(user_turn)["params"]["model"] == "deep-model"
    assert len(jev.states) == 1


def test_tui_collaboration_model_matches_routed_model():
    instance, _, _ = proxy()
    request = turn()
    request["params"]["collaborationMode"] = {
        "mode": "default",
        "settings": {"model": "old-model", "reasoning_effort": "medium"},
    }
    params = instance.client_message(request)["params"]
    assert params["model"] == "deep-model"
    assert params["effort"] == "high"
    assert params["collaborationMode"]["settings"]["model"] == "deep-model"
    assert params["collaborationMode"]["settings"]["reasoning_effort"] == "high"
