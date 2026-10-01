"""The cost controls: disk cache, case filters, budget cap, crash safety, and the stop tool.
All offline with the fake client, so none of these tests can spend money."""
import json

import pytest

from agents.rfp import agent as rfp
from agents.rfp import tools
from core import config
from core.agent import run_agent
from evals import cache, runner
from tests.fakes import FakeClient, text_response, tool_response


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("EVAL_OUT_DIR", str(tmp_path / "out"))
    return tmp_path


def use_client(monkeypatch, client):
    monkeypatch.setattr(config, "get_client", lambda: client)


def test_cache_roundtrip_and_key_sensitivity(sandbox):
    k = cache.key("prompt", "model", "question", 0)
    assert cache.get(k) is None
    cache.put(k, {"answer": "x"})
    assert cache.get(k) == {"answer": "x"}
    assert cache.key("prompt2", "model", "question", 0) != k      # prompt change invalidates
    assert cache.key("prompt", "model", "question", 1) != k       # each run index is its own sample


def test_fingerprint_changes_when_a_file_changes(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("90 days")
    before = cache.fingerprint([f])
    f.write_text("30 days")
    assert cache.fingerprint([f]) != before


def test_second_identical_run_is_free(sandbox, monkeypatch):
    client = FakeClient([text_response("We use SAML.")])          # only ONE response available
    use_client(monkeypatch, client)
    runner.main(["hello", "--only", "sso_basic"])
    assert len(client.calls) == 1
    runner.main(["hello", "--only", "sso_basic"])                 # would raise IndexError if it called again
    assert len(client.calls) == 1


def test_no_cache_flag_forces_a_fresh_call(sandbox, monkeypatch):
    client = FakeClient([text_response("a"), text_response("b")])
    use_client(monkeypatch, client)
    runner.main(["hello", "--only", "sso_basic"])
    runner.main(["hello", "--only", "sso_basic", "--no-cache"])
    assert len(client.calls) == 2


def test_runs_are_cached_separately(sandbox, monkeypatch):
    client = FakeClient([text_response("a"), text_response("b"), text_response("c")])
    use_client(monkeypatch, client)
    runner.main(["hello", "--only", "sso_basic", "--runs", "3"])
    assert len(client.calls) == 3                                 # 3 samples, not 1 sample copied 3 times


def test_budget_cap_stops_the_run(sandbox, monkeypatch):
    client = FakeClient([text_response("a"), text_response("b"), text_response("c")])
    use_client(monkeypatch, client)
    code = runner.main(["hello", "--only", "sso_basic", "--runs", "3", "--max-cost", "0.0000001"])
    assert code == 2 and len(client.calls) == 1
    saved = json.loads(next((sandbox / "out").glob("hello_*.json")).read_text())
    assert saved["stopped_on_budget"] is True


def test_a_crash_becomes_a_failed_row_not_a_dead_eval(sandbox, monkeypatch):
    class Boom:
        messages = None

        def __init__(self):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("network down")

    use_client(monkeypatch, Boom())
    assert runner.main(["hello", "--only", "sso_basic", "--min-pass-rate", "1"]) == 1
    saved = json.loads(next((sandbox / "out").glob("hello_*.json")).read_text())
    assert "network down" in saved["rows"][0]["error"]


def test_case_filters():
    cases = [{"id": "a", "tags": ["smoke"]}, {"id": "b"}]
    assert [c["id"] for c in runner.select_cases(cases, None, "smoke")] == ["a"]
    assert [c["id"] for c in runner.select_cases(cases, "b", None)] == ["b"]
    with pytest.raises(SystemExit):
        runner.select_cases(cases, "zzz", None)


def test_stop_after_tool_skips_the_final_model_call():
    tools.ANSWERS.clear()
    client = FakeClient([
        tool_response("search_docs", {"query": "x"}, "t1"),
        tool_response("record_answer", {"question_id": "q", "answer": "Done.", "citations": [],
                                        "confidence": "low", "needs_human": True, "reason": "r"}, "t2"),
    ])   # no third response: a third model call would raise IndexError
    r = run_agent(rfp.SYSTEM, "q", rfp.registry, client=client, stop_after_tool="record_answer")
    assert r["answer"] == "Done." and r["steps"] == 2 and r["stop_reason"] == "stop_tool"


def test_stop_after_tool_does_not_stop_on_a_failed_tool():
    tools.ANSWERS.clear()
    client = FakeClient([
        tool_response("record_answer", {"question_id": "q", "answer": "x", "citations": [],
                                        "confidence": "high", "needs_human": False, "reason": ""}, "t1"),
        text_response("Retrying properly."),
    ])   # invalid (no citations), so the tool errors and the loop must continue
    r = run_agent(rfp.SYSTEM, "q", rfp.registry, client=client, stop_after_tool="record_answer")
    assert r["stop_reason"] == "end_turn" and r["steps"] == 2
