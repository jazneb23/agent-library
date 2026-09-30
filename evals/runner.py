"""Run eval cases against an agent and score them.

Usage:
  python -m evals.runner hello
  python -m evals.runner rfp --tag smoke --runs 1 --max-cost 0.25   (cheap, for iterating)
  python -m evals.runner rfp --only q06,q12                        (just these cases)
  python -m evals.runner rfp --runs 3                              (full, for milestones)
  python -m evals.runner rfp --decider cascade                     (claude, jev, or cascade)

Cost controls: results are cached on disk (unchanged cases replay for free, --no-cache to
force fresh calls) and --max-cost stops the run once agent plus judge spend passes the cap.

An agent package agents/<name>/agent.py must expose:
  SYSTEM            the system prompt (string)
  registry          a ToolRegistry
  build_input(case) turns a case into the user message
and may expose STOP_AFTER_TOOL (end the run when that tool succeeds) and DATA_DIR (its docs).
Cases live in evals/cases/<name>.json."""
import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

from core import config, decisions
from core.agent import run_agent
from evals import cache
from evals import checks as eval_checks
from evals.checks import evaluate

# Settings that change agent behavior without changing any file. They go into the cache key.
BEHAVIOR_ENV = ["DECIDER", "COMPANY", "EMBEDDER", "RFP_MIN_SCORE", "RFP_TOP_K", "RFP_DATA_DIR",
                "AGENT_MAX_STEPS", "AGENT_MAX_TOKENS"]


def load_cases(name: str) -> list[dict]:
    with open(f"evals/cases/{name}.json", encoding="utf-8") as f:
        return json.load(f)


def select_cases(cases: list[dict], only: str | None, tag: str | None) -> list[dict]:
    if only:
        wanted = [s.strip() for s in only.split(",")]
        unknown = set(wanted) - {c["id"] for c in cases}
        if unknown:
            raise SystemExit(f"Unknown case ids: {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in wanted]
    if tag:
        cases = [c for c in cases if tag in c.get("tags", [])]
    return cases


def fingerprint(agent_name: str, module) -> str:
    """Hash of the code and docs that shape this agent's behavior."""
    files = list(Path("core").glob("*.py")) + list(Path("agents", agent_name).glob("*.py"))
    data_dir = getattr(module, "DATA_DIR", None)
    if data_dir:
        files += list(Path(data_dir).glob("*.md"))
    return cache.fingerprint(files)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("agent")
    p.add_argument("--runs", type=int, default=1, help="repeat each case to measure variance")
    p.add_argument("--only", help="comma separated case ids to run")
    p.add_argument("--tag", help="run only cases carrying this tag, for example smoke")
    p.add_argument("--max-cost", type=float, default=None, help="stop once spend passes this many dollars")
    p.add_argument("--no-cache", action="store_true", help="ignore cached results and call the model")
    p.add_argument("--min-pass-rate", type=float, default=0.0)
    p.add_argument("--decider", choices=["claude", "jev", "cascade"], default=None,
                   help="decision layer backend for agents that use core/decisions.py")
    args = p.parse_args(argv)

    # Evals cannot wait for a human to type y. Force it (setdefault would let a stray
    # APPROVAL_MODE=prompt in the shell freeze the run). Fake write tools only.
    os.environ["APPROVAL_MODE"] = "auto_approve"
    if args.decider:
        os.environ["DECIDER"] = args.decider
    decisions.reset_stats()
    eval_checks.reset_judge_stats()

    module = importlib.import_module(f"agents.{args.agent}.agent")
    cases = select_cases(load_cases(args.agent), args.only, args.tag)
    if not cases:
        raise SystemExit("No cases selected.")
    stop_tool = getattr(module, "STOP_AFTER_TOOL", None)
    fp = fingerprint(args.agent, module)
    env = {k: os.getenv(k) for k in BEHAVIOR_ENV}

    js = eval_checks.JUDGE_STATS
    rows, passed_runs = [], 0
    spent = saved = 0.0      # spent: real agent cost this run. saved: what cached replays would have cost.
    cached_runs, stopped = 0, False

    for case in cases:
        for i in range(args.runs):
            if args.max_cost is not None and spent + js["usd"] > args.max_cost:
                stopped = True
                break
            user_message = module.build_input(case)
            # The run index is part of the key, so --runs 3 still gives 3 different samples.
            k = cache.key(module.SYSTEM, module.registry.api_schemas(), config.MODEL, user_message,
                          stop_tool, fp, env, i)
            result = None if args.no_cache else cache.get(k)
            cached = result is not None
            if not cached:
                try:
                    result = run_agent(module.SYSTEM, user_message, module.registry,
                                       stop_after_tool=stop_tool)
                    cache.put(k, result)   # saved at once, so a crash later never loses paid results
                except Exception as e:     # one broken run becomes a failed row, not a dead eval
                    result = {"answer": "", "steps": 0, "cost_usd": 0.0, "run_id": None,
                              "tools_called": [], "tool_events": [], "error": f"{type(e).__name__}: {e}"}
            cost = result.get("cost_usd") or 0.0
            if cached:
                cached_runs, saved = cached_runs + 1, saved + cost
            else:
                spent += cost

            checks = evaluate(result, case["checks"])
            ok = all(c.passed for c in checks) and "error" not in result
            passed_runs += ok
            rows.append({"case": case["id"], "run": i + 1, "passed": ok, "steps": result["steps"],
                         "cost_usd": cost, "cached": cached, "run_id": result.get("run_id"),
                         "answer": result["answer"], "error": result.get("error"),
                         "checks": [c.__dict__ for c in checks]})
            print(f"{'PASS' if ok else 'FAIL'}  {case['id']:<24} run {i + 1}  steps={result['steps']}  "
                  f"${cost}{'  (cached)' if cached else ''}")
            if result.get("error"):
                print(f"      error: {result['error']}")
            for c in checks:
                if not c.passed:
                    print(f"      failed {c.name}: {c.detail}")
        if stopped:
            break

    total = len(rows)
    rate = passed_runs / total if total else 0.0
    ds = decisions.STATS
    if stopped:
        print(f"\nSTOPPED: spend passed the --max-cost cap of ${args.max_cost}. "
              f"{total} runs completed, results below are partial.")
    print(f"\nPass rate: {passed_runs}/{total} = {rate:.0%}")
    print(f"Spent this run: agent ${spent:.4f} + judge ${js['usd']:.4f} ({js['calls']} calls) "
          f"= ${spent + js['usd']:.4f}")
    print(f"Replayed from cache: {cached_runs} runs (would have cost ${saved:.4f})")
    print(f"Decision layer ({os.getenv('DECIDER', 'claude')}): {ds['calls']} calls, "
          f"${ds['usd']:.4f}, {ds['seconds']:.1f}s total")

    out_dir = os.getenv("EVAL_OUT_DIR", "runs/evals")
    os.makedirs(out_dir, exist_ok=True)
    path = f"{out_dir}/{args.agent}_{int(time.time())}.json"
    with open(path, "w", encoding="utf-8") as f:
        summary = {"agent": args.agent, "model": config.MODEL, "decider": os.getenv("DECIDER", "claude"),
                   "pass_rate": rate, "stopped_on_budget": stopped, "spent_agent_usd": spent,
                   "judge_cost_usd": js["usd"], "judge_calls": js["calls"], "cached_runs": cached_runs,
                   "decision_stats": dict(ds), "rows": rows}
        json.dump(summary, f, indent=2)
    print(f"Saved {path}")
    if stopped:
        return 2
    return 0 if rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    sys.exit(main())
