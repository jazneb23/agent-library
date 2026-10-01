"""Measure a decision backend against labeled questions, on YOUR data.

  python -m evals.decisions rfp --decider claude      (set DECIDER_CLAUDE_MODEL to pick the Claude model)
  python -m evals.decisions rfp --decider jev
  python -m evals.decisions rfp --decider cascade --max-cost 0.20

For each labeled question it runs the real retrieval, asks the four triage questions in one
call, and compares each answer to the label. Reported per backend: accuracy, accuracy when the
backend is confident versus not (is its confidence worth trusting?), latency, cost per 1,000
decisions, and for the cascade the escalation rate. Calls are cached and capped like agent evals."""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from agents.rfp.decisions import COVERAGE, QUESTIONS, build_state
from agents.rfp.retriever import Retriever
from core import decisions
from core.decisions import get_decider
from evals import cache

LABELS = "data/_answer_keys/rfp_triage_labels.csv"   # answer key: only evals may read it
CONFIDENT = 0.8   # Choice and Score: confidence at or above this. Noul: probability 0.8+ or 0.2-.
NAMES = list(QUESTIONS)


def load_labels() -> list[dict]:
    with open(LABELS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def make_retriever() -> Retriever:
    return Retriever()


def predict(raw: dict, label: dict) -> dict:
    """Compare each decision to its label. Returns {name: (correct, confident)}."""
    out = {}
    r = raw["route"]
    out["route"] = (r["value"] == label["route"], (r["confidence"] or 0) >= CONFIDENT)
    c = raw["coverage"]
    level = COVERAGE[min(max(round(float(c["value"])), 0), len(COVERAGE) - 1)]
    out["coverage"] = (level == label["coverage"], (c["confidence"] or 0) >= CONFIDENT)
    for name in ("injection", "compliance"):
        p = float(raw[name]["value"])
        out[name] = ((p >= 0.5) == bool(int(label[name])), p >= CONFIDENT or p <= 1 - CONFIDENT)
    return out


def rate(hits: int, total: int) -> str:
    return f"{hits}/{total} = {hits / total:.0%}" if total else "n/a"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("agent", choices=["rfp"])
    p.add_argument("--decider", choices=["claude", "jev", "cascade"], required=True)
    p.add_argument("--limit", type=int, default=None, help="only the first N labeled questions")
    p.add_argument("--max-cost", type=float, default=None,
                   help="stop once real spend passes this many dollars")
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args(argv)

    decider = get_decider(args.decider)
    retriever = make_retriever()
    labels = load_labels()[: args.limit]
    models = {k: os.getenv(k) for k in ("DECIDER_CLAUDE_MODEL", "JEV_PRICE_IN_PER_M", "AGENT_MODEL")}
    # Editing the decision code must invalidate cached answers, or a fix would replay old results.
    code = cache.fingerprint([Path("core/decisions.py"), Path("core/decisions_jev.py"),
                              Path("agents/rfp/decisions.py")])

    tally = {n: {"ok": 0, "n": 0} for n in NAMES}
    conf = {"ok": 0, "n": 0}      # accuracy when the backend says it is confident
    unsure = {"ok": 0, "n": 0}    # accuracy when it is not
    spent = saved = seconds = usd = 0.0
    escalated = total_decisions = cached_rows = invalid = 0
    misses, stopped = [], False

    for row in labels:
        if args.max_cost is not None and spent > args.max_cost:
            stopped = True
            break
        hits = retriever.search(row["question"])
        state = build_state(row["question"], hits)
        k = cache.key("triage", decider.name, models, state, repr(QUESTIONS),
                      getattr(decider, "threshold", None), code)
        entry = None if args.no_cache else cache.get(k)
        cached = entry is not None
        if not cached:
            before = dict(decisions.STATS)
            try:
                out = decider.decide(state, QUESTIONS)
                raw, error = {n: {"value": d.value, "confidence": d.confidence, "escalated": d.escalated}
                              for n, d in out.items()}, None
            except ValueError as e:   # a malformed answer is a result to count, not a reason to crash
                raw, error = None, str(e)
            entry = {"raw": raw, "error": error,
                     "usd": decisions.STATS["usd"] - before["usd"],
                     "seconds": decisions.STATS["seconds"] - before["seconds"]}
            cache.put(k, entry)
        if cached:
            cached_rows, saved = cached_rows + 1, saved + entry["usd"]
        else:
            spent += entry["usd"]
        usd += entry["usd"]
        seconds += entry["seconds"]

        if entry["raw"] is None:   # malformed output: every decision for this question counts as wrong
            invalid += 1
            misses.append(f"{row['id']}: INVALID OUTPUT ({entry['error']})")
            results = {n: (False, False) for n in NAMES}
        else:
            results = predict(entry["raw"], row)
        for name, (ok, confident) in results.items():
            tally[name]["ok"] += ok
            tally[name]["n"] += 1
            bucket = conf if confident else unsure
            bucket["ok"] += ok
            bucket["n"] += 1
            total_decisions += 1
            if entry["raw"] is not None:
                escalated += bool(entry["raw"][name]["escalated"])
                if not ok:
                    misses.append(f"{row['id']} {name}: got {entry['raw'][name]['value']!r}, "
                                  f"expected {row[name]!r} (confident={confident})")

    n_rows = len(labels) if not stopped else sum(t["n"] for t in tally.values()) // len(NAMES)
    all_ok = sum(t["ok"] for t in tally.values())
    print(f"\nBackend: {decider.name}   questions: {n_rows}   decisions: {total_decisions}")
    for name in NAMES:
        print(f"  {name:<11} accuracy {rate(tally[name]['ok'], tally[name]['n'])}")
    print(f"Overall accuracy:              {rate(all_ok, total_decisions)}")
    print(f"  when confident:              {rate(conf['ok'], conf['n'])}")
    print(f"  when not confident:          {rate(unsure['ok'], unsure['n'])}")
    print(f"Malformed outputs:             {rate(invalid, n_rows)} of questions")
    print(f"Avg latency per question:      {seconds / max(n_rows, 1):.2f}s")
    print(f"Cost per 1,000 decisions:      ${usd / max(total_decisions, 1) * 1000:.4f}")
    if args.decider == "cascade":
        print(f"Escalation rate:               {rate(escalated, total_decisions)}")
    print(f"Spent this run: ${spent:.4f}   replayed from cache: {cached_rows} questions "
          f"(would have cost ${saved:.4f})")
    if stopped:
        print(f"STOPPED: real spend passed the --max-cost cap of ${args.max_cost}. Results are partial.")
    if misses:
        print(f"\nMisses ({len(misses)}):")
        for m in misses[:20]:
            print("  ", m)

    out_dir = os.getenv("EVAL_OUT_DIR", "runs/evals")
    os.makedirs(out_dir, exist_ok=True)
    path = f"{out_dir}/decisions_{args.decider}_{int(time.time())}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"decider": args.decider, "models": models, "questions": n_rows,
                   "accuracy": {n: tally[n] for n in NAMES}, "overall": {"ok": all_ok, "n": total_decisions},
                   "confident": conf, "not_confident": unsure, "usd_total": usd, "spent_this_run": spent,
                   "avg_seconds": seconds / max(n_rows, 1), "escalated": escalated, "invalid": invalid,
                   "misses": misses,
                   "stopped_on_budget": stopped}, f, indent=2)
    print(f"Saved {path}")
    return 2 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
