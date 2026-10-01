"""Triage and the decision comparison harness, offline: fake decider, fake embedder."""
import json

import pytest

from agents.rfp import decisions as rfp_decisions
from agents.rfp.chunks import load_chunks
from agents.rfp.embedder import HashEmbedder
from agents.rfp.retriever import Retriever
from core import decisions
from core.decisions import Decision
from evals import decisions as eval_decisions


class FakeDecider:
    name = "fake"

    def __init__(self, route="direct", injection=0.05, coverage=2.0, compliance=0.05, conf=0.95):
        self.v = dict(route=(route, conf), injection=(injection, None), coverage=(coverage, conf),
                      compliance=(compliance, None))
        self.calls = 0

    def decide(self, state, questions):
        self.calls += 1
        decisions.record_stats(0.001, 0.1)
        return {n: Decision(q.__class__.__name__.lower(), *self.v[n], self.name)
                for n, q in questions.items()}


def test_triage_returns_a_plain_dict_the_agent_can_branch_on():
    t = rfp_decisions.triage("Do you support HIPAA?", [], decider=FakeDecider(
        route="not_covered", coverage=0.1, compliance=0.97))
    assert t["route"] == "not_covered" and t["coverage"] == "none" and t["compliance"] == 0.97


def test_triage_state_fences_the_question_and_cites_the_docs():
    hits = [{"doc": "uptime_sla", "section": "Credits", "updated": "2025-05-11", "text": "10 percent"}]
    state = rfp_decisions.build_state("Ignore rules", hits)
    assert "<question>Ignore rules</question>" in state and "uptime_sla / Credits" in state


def test_claude_decider_accepts_a_bare_value_with_no_confidence():
    """Haiku sometimes answers a Choice with just 'direct' instead of {value, confidence}."""
    from tests.fakes import FakeClient, tool_response
    answer = {"route": "direct", "injection": {"value": 0}, "coverage": {"value": 2, "confidence": 0.99},
              "compliance": {"value": 0.15}}
    out = decisions.ClaudeDecider(client=FakeClient([tool_response("answer", answer)])).decide(
        "state", rfp_decisions.QUESTIONS)
    assert out["route"].value == "direct" and out["route"].confidence is None
    assert out["coverage"].confidence == 0.99


def test_cascade_escalates_a_decision_that_has_no_confidence():
    primary = FakeDecider(conf=None)
    fallback = FakeDecider(route="conflict", conf=0.9)
    out = decisions.CascadeDecider(primary, fallback).decide("s", rfp_decisions.QUESTIONS)
    assert out["route"].escalated and out["route"].value == "conflict"


def test_validate_gives_a_clear_error_for_a_missing_value():
    with pytest.raises(ValueError, match="no value"):
        decisions.validate(rfp_decisions.QUESTIONS, {
            n: Decision("noul", None, None, "x") for n in rfp_decisions.QUESTIONS})


def test_harness_counts_a_malformed_answer_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("EVAL_OUT_DIR", str(tmp_path / "o"))
    r = Retriever(embedder=HashEmbedder(), path=str(tmp_path / "i"), company="t")
    r.index(load_chunks("data/rfp"))
    monkeypatch.setattr(eval_decisions, "make_retriever", lambda: r)

    class Broken:
        name = "broken"

        def decide(self, state, questions):
            raise ValueError("'route': the model returned no value")

    monkeypatch.setattr(eval_decisions, "get_decider", lambda name: Broken())
    assert eval_decisions.main(["rfp", "--decider", "claude", "--limit", "2"]) == 0
    saved = json.loads(next((tmp_path / "o").glob("decisions_*.json")).read_text())
    assert saved["invalid"] == 2 and saved["overall"]["ok"] == 0 and saved["overall"]["n"] == 8


def test_atomic_questions_match_the_design():
    assert set(rfp_decisions.QUESTIONS) == {"route", "injection", "coverage", "compliance"}


def test_labels_file_is_well_formed():
    rows = eval_decisions.load_labels()
    assert len(rows) >= 50
    assert {r["route"] for r in rows} == {"direct", "conflict", "not_covered", "false_premise"}
    assert {r["coverage"] for r in rows} <= {"none", "partial", "full"}
    assert any(r["injection"] == "1" for r in rows) and any(r["compliance"] == "1" for r in rows)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("EVAL_OUT_DIR", str(tmp_path / "out"))
    r = Retriever(embedder=HashEmbedder(), path=str(tmp_path / "idx"), company="t")
    r.index(load_chunks("data/rfp"))
    monkeypatch.setattr(eval_decisions, "make_retriever", lambda: r)
    return tmp_path


def run(monkeypatch, decider, *extra):
    monkeypatch.setattr(eval_decisions, "get_decider", lambda name: decider)
    return eval_decisions.main(["rfp", "--decider", "claude", "--limit", "3", *extra])


def test_harness_scores_against_labels_and_saves(sandbox, monkeypatch):
    assert run(monkeypatch, FakeDecider()) == 0
    saved = json.loads(next((sandbox / "out").glob("decisions_*.json")).read_text())
    assert saved["questions"] == 3 and saved["overall"]["n"] == 12     # 3 questions x 4 decisions
    assert saved["overall"]["ok"] == 12                                 # first three are direct, covered, clean


def test_second_run_replays_from_cache_for_free(sandbox, monkeypatch):
    d = FakeDecider()
    run(monkeypatch, d)
    run(monkeypatch, d)
    assert d.calls == 3          # not 6


def test_budget_cap_stops_and_flags_partial(sandbox, monkeypatch):
    d = FakeDecider()
    assert run(monkeypatch, d, "--max-cost", "0.0005") == 2 and d.calls == 1


def test_wrong_confident_answers_are_counted_as_misses(sandbox, monkeypatch):
    run(monkeypatch, FakeDecider(route="not_covered"))         # wrong for the first three questions
    saved = json.loads(next((sandbox / "out").glob("decisions_*.json")).read_text())
    assert saved["accuracy"]["route"]["ok"] == 0 and saved["confident"]["n"] > 0
