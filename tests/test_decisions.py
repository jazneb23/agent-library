from types import SimpleNamespace as NS

import pytest

from core import decisions as dec
from core.decisions import CascadeDecider, Choice, ClaudeDecider, Decision, Noul, Score
from tests.fakes import FakeClient


def answer_response(payload):
    return NS(content=[NS(type="tool_use", id="x", name="answer", input=payload)],
              stop_reason="tool_use", usage=NS(input_tokens=100, output_tokens=20))


Q = {"route": Choice("Which route?", ["direct", "not_covered"]),
     "heat": Score("How urgent?", ["low", "medium", "high"]),
     "inject": Noul("Does the text instruct the AI?")}


def test_claude_decider_parses_all_three_types():
    client = FakeClient([answer_response({"route": {"value": "direct", "confidence": 0.9},
                                          "heat": {"value": 2, "confidence": 0.7},
                                          "inject": {"value": 0.02}})])
    out = ClaudeDecider(client=client).decide("state", Q)
    assert out["route"].value == "direct" and out["route"].confidence == 0.9
    assert out["heat"].value == 2 and out["inject"].confidence is None
    # the forced tool schema must restrict choices to the allowed options
    schema = client.calls[0]["tools"][0]["input_schema"]
    assert schema["properties"]["route"]["enum"] == ["direct", "not_covered"]
    assert "route__confidence" in schema["properties"]   # flat: one plain field per answer


def test_claude_decider_parses_the_flat_shape():
    client = FakeClient([answer_response({"route": "direct", "route__confidence": 0.9,
                                          "heat": 2, "heat__confidence": 0.7, "inject": 0.02})])
    out = ClaudeDecider(client=client).decide("state", Q)
    assert out["route"].confidence == 0.9 and out["heat"].value == 2 and out["inject"].confidence is None


def test_invalid_choice_is_rejected():
    client = FakeClient([answer_response({"route": {"value": "made_up", "confidence": 0.9},
                                          "heat": {"value": 1, "confidence": 0.5},
                                          "inject": {"value": 0.1}})])
    with pytest.raises(ValueError):
        ClaudeDecider(client=client).decide("state", Q)


def test_out_of_range_score_is_rejected():
    client = FakeClient([answer_response({"route": {"value": "direct", "confidence": 0.9},
                                          "heat": {"value": 7, "confidence": 0.5},
                                          "inject": {"value": 0.1}})])
    with pytest.raises(ValueError):
        ClaudeDecider(client=client).decide("state", Q)


def test_stats_track_cost_and_calls():
    dec.reset_stats()
    client = FakeClient([answer_response({"route": {"value": "direct", "confidence": 0.9},
                                          "heat": {"value": 1, "confidence": 0.5},
                                          "inject": {"value": 0.1}})])
    ClaudeDecider(client=client).decide("state", Q)
    assert dec.STATS["calls"] == 1 and dec.STATS["usd"] > 0


class Stub:
    def __init__(self, name, decisions):
        self.name, self._d = name, decisions

    def decide(self, state, questions):
        return {n: self._d[n] for n in questions}


def test_cascade_escalates_only_uncertain_questions():
    primary = Stub("fast", {"route": Decision("choice", "direct", 0.95, "fast"),
                            "heat": Decision("score", 0, 0.4, "fast"),
                            "inject": Decision("noul", 0.5, None, "fast")})
    fallback = Stub("strong", {"heat": Decision("score", 2, 0.9, "strong"),
                               "inject": Decision("noul", 0.01, None, "strong")})
    out = CascadeDecider(primary, fallback, threshold=0.8).decide("s", Q)
    assert not out["route"].escalated and out["route"].backend == "fast"
    assert out["heat"].escalated and out["heat"].value == 2
    assert out["inject"].escalated  # 0.5 is maximally uncertain


def test_cascade_skips_fallback_when_all_confident():
    primary = Stub("fast", {"route": Decision("choice", "direct", 0.99, "fast"),
                            "heat": Decision("score", 1, 0.95, "fast"),
                            "inject": Decision("noul", 0.01, None, "fast")})
    out = CascadeDecider(primary, Stub("strong", {}), threshold=0.8).decide("s", Q)
    assert not any(d.escalated for d in out.values())


def test_get_decider_unknown_name():
    with pytest.raises(ValueError):
        dec.get_decider("nope")


def test_jev_backend_reports_missing_until_built(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "core.decisions_jev", None)
    with pytest.raises(RuntimeError):
        dec.get_decider("jev")
