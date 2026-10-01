"""A batch run survives one broken question."""
from agents.rfp import run_all, tools


def test_one_failing_question_is_recorded_for_a_human_and_the_run_continues(monkeypatch):
    tools.ANSWERS.clear()

    def fake_run_case(case):
        if case["id"] == "q02":
            raise RuntimeError("model API timed out")
        tools.record_answer(case["id"], "ok", ["a / b"], "high", False, "")
        return {"cost_usd": 0.01, "steps": 2}

    monkeypatch.setattr(run_all, "run_case", fake_run_case)
    monkeypatch.setattr(run_all, "ask_approval", lambda *a, **k: False)   # no export, no prompt
    run_all.main(["--limit", "3"])
    assert tools.ANSWERS["q02"]["needs_human"] is True and "timed out" in tools.ANSWERS["q02"]["reason"]
    assert "q01" in tools.ANSWERS and "q03" in tools.ANSWERS
