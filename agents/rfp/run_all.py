"""Run every question in the company's questionnaire and write runs/rfp_answers.json.
  python -m agents.rfp.run_all            all questions
  python -m agents.rfp.run_all --limit 5  first five only"""
import argparse
import csv

from agents.rfp import settings, tools
from agents.rfp.agent import STOP_AFTER_TOOL, SYSTEM, build_input, registry
from core.agent import run_agent
from core.approval import ask_approval


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    with open(f"{settings.DATA_DIR}/questionnaire.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[: args.limit]

    tools.ANSWERS.clear()
    total = 0.0
    for row in rows:
        # Only id and question are used. The category column is deliberately ignored.
        r = run_agent(SYSTEM, build_input({"id": row["id"], "input": row["question"]}), registry,
                      stop_after_tool=STOP_AFTER_TOOL)
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
