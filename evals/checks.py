"""Eval checks. Each check is a small pure function, so it is easy to test.
Prefer deterministic checks. Use judge_rubric only for fuzzy qualities."""
from dataclasses import dataclass

from core import config
from evals import cache


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def _lower(text: str) -> str:
    return (text or "").lower()


JUDGE_STATS = {"calls": 0, "usd": 0.0}   # grading has a cost too, so the runner reports it


def reset_judge_stats() -> None:
    JUDGE_STATS.update(calls=0, usd=0.0)


def judge(answer: str, rubric: str, client=None) -> tuple[bool, str]:
    """A second model call grades the answer against a rubric. The judge can be
    wrong too, so use it sparingly and read its reasons."""
    # Identical answer and rubric get the identical verdict for free. Skipped when a client is
    # passed in (tests), so tests never touch the disk cache.
    k = cache.key("judge", config.JUDGE_MODEL, rubric, answer) if client is None else None
    if k and (hit := cache.get(k)):
        return hit["ok"], hit["text"]
    client = client or config.get_client()
    response = client.messages.create(
        model=config.JUDGE_MODEL, max_tokens=200,
        system="You grade AI outputs. Reply with PASS or FAIL, then a colon, then one short reason.",
        messages=[{"role": "user", "content": f"Rubric: {rubric}\n\nOutput to grade:\n{answer}"}])
    JUDGE_STATS["calls"] += 1
    JUDGE_STATS["usd"] += config.cost_usd(response.usage.input_tokens, response.usage.output_tokens,
                                          config.JUDGE_MODEL)
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    ok = text.upper().startswith("PASS")
    if k:
        cache.put(k, {"ok": ok, "text": text})
    return ok, text


def _last_recorded_answer(result: dict) -> dict | None:
    """The input of the agent's final record_answer call, read from the tool log."""
    calls = [e["input"] for e in result.get("tool_events", []) if e["tool"] == "record_answer"]
    return calls[-1] if calls else None


def evaluate(result: dict, checks: dict, judge_fn=judge) -> list[CheckResult]:
    out: list[CheckResult] = []
    answer = _lower(result.get("answer", ""))
    called = result.get("tools_called", [])

    if "answer_contains_any" in checks:
        hit = [s for s in checks["answer_contains_any"] if s.lower() in answer]
        out.append(CheckResult("answer_contains_any", bool(hit), f"matched {hit}" if hit else "no match"))
    if "answer_contains_all" in checks:
        missing = [s for s in checks["answer_contains_all"] if s.lower() not in answer]
        out.append(CheckResult("answer_contains_all", not missing, f"missing {missing}" if missing else ""))
    if "answer_not_contains" in checks:
        bad = [s for s in checks["answer_not_contains"] if s.lower() in answer]
        out.append(CheckResult("answer_not_contains", not bad, f"found forbidden {bad}" if bad else ""))
    if "must_call_tools" in checks:
        missing = [t for t in checks["must_call_tools"] if t not in called]
        out.append(CheckResult("must_call_tools", not missing, f"not called {missing}" if missing else ""))
    if "must_not_call_tools" in checks:
        bad = [t for t in checks["must_not_call_tools"] if t in called]
        out.append(CheckResult("must_not_call_tools", not bad, f"called forbidden {bad}" if bad else ""))
    if "needs_human" in checks:   # did the agent route this one to a person, as expected?
        rec = _last_recorded_answer(result)
        if rec is None:
            out.append(CheckResult("needs_human", False, "record_answer was never called"))
        else:
            got = rec.get("needs_human")
            out.append(CheckResult("needs_human", got == checks["needs_human"],
                                   f"expected {checks['needs_human']}, got {got}"))
    if "cites" in checks:         # every named doc must appear in the recorded citations
        rec = _last_recorded_answer(result)
        cited = " | ".join(rec.get("citations", [])).lower() if rec else ""
        missing = [d for d in checks["cites"] if d.lower() not in cited]
        out.append(CheckResult("cites", not missing, f"not cited {missing}" if missing else ""))
    if "max_steps" in checks:
        ok = result.get("steps", 0) <= checks["max_steps"]
        out.append(CheckResult("max_steps", ok, f"{result.get('steps')} steps"))
    if "max_cost_usd" in checks:
        cost = result.get("cost_usd") or 0
        out.append(CheckResult("max_cost_usd", cost <= checks["max_cost_usd"], f"${cost}"))
    if "judge_rubric" in checks:
        ok, reason = judge_fn(result.get("answer", ""), checks["judge_rubric"])
        out.append(CheckResult("judge_rubric", ok, reason))
    return out
