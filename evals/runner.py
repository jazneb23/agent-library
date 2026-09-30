"""Run eval cases against an agent and score them.

Usage:
  python -m evals.runner hello
  python -m evals.runner hello --runs 3 --min-pass-rate 0.8
  python -m evals.runner rfp --decider cascade      (claude, jev, or cascade)

An agent package agents/<name>/agent.py must expose:
  SYSTEM            the system prompt (string)
  registry          a ToolRegistry
  build_input(case) turns a case into the user message
Cases live in evals/cases/<name>.json."""
import argparse
import importlib
import json
import os
import sys
import time

from core import decisions
from core.agent import run_agent
from evals.checks import evaluate


def load_cases(name: str) -> list[dict]:
    with open(f"evals/cases/{name}.json", encoding="utf-8") as f:
        return json.load(f)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("agent")
    p.add_argument("--runs", type=int, default=1, help="repeat each case to measure variance")
    p.add_argument("--min-pass-rate", type=float, default=0.0)
    p.add_argument("--decider", choices=["claude", "jev", "cascade"], default=None,
                   help="decision layer backend for agents that use core/decisions.py")
    args = p.parse_args(argv)

    # Evals cannot wait for a human to type y. Fake write tools are auto approved.
    os.environ.setdefault("APPROVAL_MODE", "auto_approve")
    if args.decider:
        os.environ["DECIDER"] = args.decider
    decisions.reset_stats()

    module = importlib.import_module(f"agents.{args.agent}.agent")
    cases = load_cases(args.agent)
    rows, passed_runs, total_cost = [], 0, 0.0

    for case in cases:
        for i in range(args.runs):
            result = run_agent(module.SYSTEM, module.build_input(case), module.registry)
            checks = evaluate(result, case["checks"])
            ok = all(c.passed for c in checks)
            passed_runs += ok
            total_cost += result["cost_usd"] or 0
            rows.append({"case": case["id"], "run": i + 1, "passed": ok, "steps": result["steps"],
                         "cost_usd": result["cost_usd"], "run_id": result["run_id"],
                         "answer": result["answer"],
                         "checks": [c.__dict__ for c in checks]})
            flag = "PASS" if ok else "FAIL"
            print(f"{flag}  {case['id']:<28} run {i + 1}  steps={result['steps']}  ${result['cost_usd']}")
            for c in checks:
                if not c.passed:
                    print(f"      failed {c.name}: {c.detail}")

    total = len(rows)
    rate = passed_runs / total if total else 0.0
    ds = decisions.STATS
    print(f"\nPass rate: {passed_runs}/{total} = {rate:.0%}   Agent cost: ${total_cost:.4f}")
    print(f"Decision layer ({os.getenv('DECIDER', 'claude')}): {ds['calls']} calls, "
          f"${ds['usd']:.4f}, {ds['seconds']:.1f}s total")

    os.makedirs("runs/evals", exist_ok=True)
    path = f"runs/evals/{args.agent}_{int(time.time())}.json"
    with open(path, "w", encoding="utf-8") as f:
        summary = {"agent": args.agent, "decider": os.getenv("DECIDER", "claude"), "pass_rate": rate,
                   "total_cost_usd": total_cost, "decision_stats": dict(ds), "rows": rows}
        json.dump(summary, f, indent=2)
    print(f"Saved {path}")
    return 0 if rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    sys.exit(main())
