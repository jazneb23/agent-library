from evals.checks import evaluate

R = {"answer": "SSO uses SAML on Enterprise.", "tools_called": ["search_docs"], "steps": 2, "cost_usd": 0.01}


def names(results):
    return {c.name: c.passed for c in results}


def test_contains_and_not_contains():
    out = names(evaluate(R, {"answer_contains_any": ["saml"], "answer_not_contains": ["soc 2"]}))
    assert out == {"answer_contains_any": True, "answer_not_contains": True}


def test_forbidden_text_fails():
    assert not evaluate(R, {"answer_not_contains": ["enterprise"]})[0].passed


def test_tool_checks():
    out = names(evaluate(R, {"must_call_tools": ["search_docs"], "must_not_call_tools": ["save_note"]}))
    assert all(out.values())
    assert not evaluate(R, {"must_call_tools": ["save_note"]})[0].passed


def test_limits():
    assert evaluate(R, {"max_steps": 2, "max_cost_usd": 0.02})[0].passed
    assert not evaluate(R, {"max_steps": 1})[0].passed


def recorded(needs_human=False, citations=("security_overview_2025 / Encryption",)):
    return {"tool_events": [{"tool": "record_answer", "input": {
        "needs_human": needs_human, "citations": list(citations)}}]}


def test_needs_human_check_reads_the_recorded_answer():
    assert evaluate(recorded(True), {"needs_human": True})[0].passed
    assert not evaluate(recorded(False), {"needs_human": True})[0].passed


def test_needs_human_fails_if_nothing_was_recorded():
    out = evaluate({"tool_events": []}, {"needs_human": False})[0]
    assert not out.passed and "never called" in out.detail


def test_cites_check_requires_every_named_doc():
    r = recorded(citations=["uptime_sla / Credits", "disaster_recovery / Objectives"])
    assert evaluate(r, {"cites": ["uptime_sla", "disaster_recovery"]})[0].passed
    assert not evaluate(r, {"cites": ["uptime_sla", "sso_identity"]})[0].passed


def test_judge_cost_is_tracked():
    from evals import checks
    from tests.fakes import FakeClient, text_response
    checks.reset_judge_stats()
    ok, _ = checks.judge("answer", "rubric", client=FakeClient([text_response("PASS: fine", 400, 40)]))
    assert ok and checks.JUDGE_STATS["calls"] == 1 and checks.JUDGE_STATS["usd"] > 0


def test_empty_judge_reply_is_reported_not_cached(tmp_path, monkeypatch):
    from core import config
    from evals import cache, checks
    from tests.fakes import FakeClient, text_response
    monkeypatch.setenv("EVAL_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "get_client", lambda: FakeClient([text_response("")]))
    ok, detail = checks.judge("answer", "rubric")
    assert not ok and "empty reply" in detail
    assert cache.get(cache.key("judge", config.JUDGE_MODEL, "rubric", "answer")) is None


def test_cost_uses_the_right_price_per_model(monkeypatch):
    from core import config
    monkeypatch.delenv("PRICE_IN_PER_M", raising=False)
    monkeypatch.delenv("PRICE_OUT_PER_M", raising=False)
    sonnet = config.cost_usd(1_000_000, 0, "claude-sonnet-5-5")
    haiku = config.cost_usd(1_000_000, 0, "claude-haiku-4-5-20251001")
    assert haiku < sonnet


def test_judge_is_pluggable():
    out = evaluate(R, {"judge_rubric": "x"}, judge_fn=lambda a, r: (True, "PASS: fine"))
    assert out[0].passed
