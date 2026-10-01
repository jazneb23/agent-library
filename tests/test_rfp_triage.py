"""Triage wired into the RFP agent. Offline: fake decider, fake Claude, fake embedder."""
import pytest

from agents.rfp import agent as rfp
from agents.rfp import settings, tools
from agents.rfp.chunks import load_chunks
from agents.rfp.embedder import HashEmbedder
from agents.rfp.retriever import Retriever
from tests.fakes import FakeClient, tool_response
from tests.test_decision_eval import FakeDecider

CASE = {"id": "q99", "input": "Will you sign a HIPAA business associate agreement?"}


def record(needs_human=False, citations=("security_overview_2025 / Encryption",)):
    return tool_response("record_answer", {"question_id": "q99", "answer": "An answer.",
                                           "citations": list(citations), "confidence": "high",
                                           "needs_human": needs_human, "reason": "r"})


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    r = Retriever(embedder=HashEmbedder(), path=str(tmp_path), company="t")
    r.index(load_chunks("data/rfp"))
    monkeypatch.setattr(tools, "_retriever", r)
    monkeypatch.delenv("DECIDER", raising=False)
    monkeypatch.delenv("RFP_INJECTION_ACTION", raising=False)
    tools.ANSWERS.clear()
    tools.RUN_CONTEXT.clear()


def test_no_decider_means_the_plain_agent_and_no_triage():
    client = FakeClient([tool_response("search_docs", {"query": "x"}, "t1"), record()])
    r = rfp.run_case(CASE, client=client)
    assert r["stop_reason"] == "stop_tool" and "triage" not in r


def test_all_three_signals_agree_so_claude_is_skipped(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.99)             # the retriever's own score is weak
    client = FakeClient([])                                       # any model call would raise
    r = rfp.run_case(CASE, decider=FakeDecider(route="not_covered", coverage=0.0), client=client)
    assert r["stop_reason"] == "triage" and r["steps"] == 0 and client.calls == []
    assert tools.ANSWERS["q99"]["needs_human"] is True
    assert r["cost_usd"] == pytest.approx(0.001)                  # only the triage call cost anything


def test_one_confident_wrong_decision_cannot_skip_a_covered_question(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.0)               # but the retriever found strong evidence
    client = FakeClient([record()])
    r = rfp.run_case(CASE, decider=FakeDecider(route="not_covered", coverage=0.0), client=client)
    assert r["stop_reason"] == "stop_tool" and len(client.calls) == 1   # Claude still got the question


def test_an_injected_question_is_never_skipped(monkeypatch):
    """A real question can hide inside injected text. Triage on that text is unreliable, so Claude answers."""
    monkeypatch.setattr(settings, "MIN_SCORE", 0.99)
    client = FakeClient([record()])
    r = rfp.run_case(CASE, decider=FakeDecider(route="not_covered", coverage=0.0, injection=0.99),
                     client=client)
    assert r["stop_reason"] == "stop_tool" and "automated screen" in client.calls[0]["messages"][0]["content"]


def test_coverage_alone_is_not_enough_to_skip(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.99)
    client = FakeClient([record()])
    r = rfp.run_case(CASE, decider=FakeDecider(route="direct", coverage=0.0), client=client)
    assert r["stop_reason"] == "stop_tool"


def test_compliance_question_must_reach_a_human_even_if_the_model_forgets(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.0)
    client = FakeClient([record(needs_human=False), record(needs_human=True, citations=())])
    r = rfp.run_case(CASE, decider=FakeDecider(compliance=0.97), client=client)
    assert tools.ANSWERS["q99"]["needs_human"] is True and r["steps"] == 2   # rejected once, then fixed
    assert tools.RUN_CONTEXT == {}                                           # context never leaks


def test_a_non_compliance_question_is_not_forced_to_a_human(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.0)
    r = rfp.run_case(CASE, decider=FakeDecider(compliance=0.02), client=FakeClient([record()]))
    assert tools.ANSWERS["q99"]["needs_human"] is False and r["steps"] == 1


def test_injection_is_flagged_to_the_model_by_default(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.0)
    client = FakeClient([record()])
    rfp.run_case(CASE, decider=FakeDecider(injection=0.96), client=client)
    assert "automated screen" in client.calls[0]["messages"][0]["content"]


def test_injection_can_be_handed_straight_to_a_human(monkeypatch):
    monkeypatch.setenv("RFP_INJECTION_ACTION", "human")
    client = FakeClient([])
    r = rfp.run_case(CASE, decider=FakeDecider(injection=0.96), client=client)
    assert r["stop_reason"] == "triage" and client.calls == [] and tools.ANSWERS["q99"]["needs_human"]


def test_a_clean_question_gets_no_injection_note(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.0)
    client = FakeClient([record()])
    rfp.run_case(CASE, decider=FakeDecider(injection=0.02), client=client)
    assert "automated screen" not in client.calls[0]["messages"][0]["content"]


# ---- conflicts, outages and the audit trail ----

CONFLICT_CASE = {"id": "q98", "input": "How long is customer data retained after contract termination?"}


def record_for(qid, needs_human, citations):
    return tool_response("record_answer", {"question_id": qid, "answer": "90 days.", "citations": citations,
                                           "confidence": "high", "needs_human": needs_human, "reason": "r"})


def test_conflict_route_forces_a_human_and_every_disagreeing_source_cited(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.0)
    both = ["security_overview_2025 / Data retention", "security_overview_2023 / Data retention"]
    client = FakeClient([
        record_for("q98", False, both),                                   # forgot to flag it
        record_for("q98", True, ["security_overview_2025 / Data retention"]),   # cited only the newest
        record_for("q98", True, both),                                    # correct
    ])
    r = rfp.run_case(CONFLICT_CASE, decider=FakeDecider(route="conflict"), client=client)
    assert r["steps"] == 3 and tools.ANSWERS["q98"]["needs_human"] is True
    assert len(tools.ANSWERS["q98"]["citations"]) == 2


def test_a_low_confidence_conflict_route_does_not_trigger_the_rule(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.0)
    client = FakeClient([record_for("q98", False, ["security_overview_2025 / Data retention"])])
    r = rfp.run_case(CONFLICT_CASE, decider=FakeDecider(route="conflict", conf=0.3), client=client)
    assert r["steps"] == 1 and tools.ANSWERS["q98"]["needs_human"] is False


class Down:
    name = "down"

    def decide(self, state, questions):
        raise RuntimeError("503 service unavailable")


def test_a_decision_service_outage_falls_back_to_the_plain_agent(monkeypatch):
    events = []
    monkeypatch.setattr(rfp, "log_event", lambda run_id, event, **kw: events.append((event, kw)))
    client = FakeClient([record()])
    r = rfp.run_case(CASE, decider=Down(), client=client)
    assert r["stop_reason"] == "stop_tool" and "503" in r["triage_error"]    # still answered
    assert events[0][0] == "triage_failed" and events[0][1]["question_id"] == "q99"


def test_every_triage_decision_is_written_to_the_audit_log(monkeypatch):
    monkeypatch.setattr(settings, "MIN_SCORE", 0.99)
    events = []
    monkeypatch.setattr(rfp, "log_event", lambda run_id, event, **kw: events.append((event, kw)))
    rfp.run_case(CASE, decider=FakeDecider(route="not_covered", coverage=0.0), client=FakeClient([]))
    name, data = events[0]
    assert name == "triage" and data["skipped_claude"] is True and data["route"] == "not_covered"
    assert {"question_id", "backend", "coverage", "injection", "compliance", "best_score", "usd"} <= set(data)
