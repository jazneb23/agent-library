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


def test_judge_is_pluggable():
    out = evaluate(R, {"judge_rubric": "x"}, judge_fn=lambda a, r: (True, "PASS: fine"))
    assert out[0].passed
