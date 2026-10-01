"""Run every question in the company's questionnaire and write runs/rfp_answers.json.
  python -m agents.rfp.run_all            all questions
  python -m agents.rfp.run_all --limit 5  first five only"""
import argparse
import csv

from agents.rfp import settings, tools
from agents.rfp.agent import run_case
from core.approval import ask_approval


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    with open(f"{settings.DATA_DIR}/questionnaire.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[: args.limit]

    tools.ANSWERS.clear()
    total = 0.0
    for row in rows:
        # Only id and question are used. The category column is deliberately ignored.
        try:
            r = run_case({"id": row["id"], "input": row["question"]})
        except Exception as e:   # one broken question must not lose the rest of the questionnaire
            tools.record_answer(row["id"], "System error. A person needs to answer this.", [], "low", True,
                                f"Agent error: {type(e).__name__}: {e}")
            print(f"{row['id']}  ERROR  {type(e).__name__}: {e}  {row['question'][:50]}")
            continue
        total += r["cost_usd"] or 0
        a = tools.ANSWERS.get(row["id"])
        flag = "HUMAN" if a and a["needs_human"] else "ok   "
        print(f"{row['id']}  {flag}  steps={r['steps']}  ${r['cost_usd']}  {row['question'][:60]}")

    # Writing the answer sheet is a write action, so it goes through the approval gate.
    if ask_approval("export_answers", {"answers": len(tools.ANSWERS)}):
        print(tools.export_answers())
    else:
        print("Export denied. Nothing written.")
    print(f"Total cost: ${total:.4f}")


if __name__ == "__main__":
    main()
