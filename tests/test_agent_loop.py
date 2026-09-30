import pytest

from core import config
from core.agent import run_agent
from core.tools import Tool, ToolRegistry
from tests.fakes import FakeClient, text_response, tool_response

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("APPROVAL_MODE", "auto_approve")


def registry(fn=lambda x: "ok", needs_approval=False):
    return ToolRegistry([Tool("t", "a tool", SCHEMA, fn, needs_approval)])


def test_answers_without_tools():
    r = run_agent("sys", "hi", registry(), client=FakeClient([text_response("hello")]))
    assert r["answer"] == "hello" and r["steps"] == 1 and r["tools_called"] == []


def test_runs_tool_then_answers():
    client = FakeClient([tool_response("t", {"x": "a"}), text_response("done")])
    r = run_agent("sys", "hi", registry(), client=client)
    assert r["tools_called"] == ["t"] and r["answer"] == "done" and r["steps"] == 2
    # the tool result must have been sent back to the model (the list is shared, so it
    # now ends with the final assistant turn and the tool result sits just before it)
    assert client.calls[1]["messages"][-2]["content"][0]["type"] == "tool_result"


def test_tool_error_is_returned_not_raised():
    def boom(x):
        raise ValueError("bad")
    client = FakeClient([tool_response("t", {"x": "a"}), text_response("recovered")])
    r = run_agent("sys", "hi", registry(boom), client=client)
    assert r["tool_events"][0]["is_error"] and "bad" in r["tool_events"][0]["output"]
    assert r["answer"] == "recovered"


def test_unknown_tool_is_an_error_result():
    client = FakeClient([tool_response("nope", {}), text_response("ok")])
    r = run_agent("sys", "hi", registry(), client=client)
    assert r["tool_events"][0]["is_error"]


def test_denied_approval_blocks_the_tool(monkeypatch):
    monkeypatch.setenv("APPROVAL_MODE", "auto_deny")
    ran = []
    client = FakeClient([tool_response("t", {"x": "a"}), text_response("ok")])
    r = run_agent("sys", "hi", registry(lambda x: ran.append(x), needs_approval=True), client=client)
    assert ran == [] and r["tool_events"][0]["is_error"]


def test_max_steps_stops_a_runaway_loop():
    client = FakeClient([tool_response("t", {"x": "a"}, tool_id=f"tu_{i}") for i in range(5)])
    r = run_agent("sys", "hi", registry(), client=client, max_steps=3)
    assert r["stop_reason"] == "max_steps" and r["steps"] == 3


def test_cost_is_tracked():
    client = FakeClient([text_response("x", tin=1_000_000, tout=0)])
    r = run_agent("sys", "hi", registry(), client=client)
    assert r["cost_usd"] == config.PRICE_IN_PER_M


def test_duplicate_tool_names_rejected():
    t = Tool("t", "d", SCHEMA, lambda x: "")
    with pytest.raises(ValueError):
        ToolRegistry([t, t])
