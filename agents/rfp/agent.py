"""RFP and security questionnaire agent. Exposes SYSTEM, registry and build_input
so the eval runner can use it. Try one question:
  python -m agents.rfp.agent "Do you encrypt customer data at rest?" """
import sys

from agents.rfp import settings, tools
from agents.rfp.prompts import build_system
from core.agent import run_agent
from core.tools import Tool, ToolRegistry

SYSTEM = build_system(settings.COMPANY_NAME)
STOP_AFTER_TOOL = "record_answer"   # the run is done once the answer is recorded (saves a model call)
DATA_DIR = settings.DATA_DIR        # the eval cache fingerprints these docs, so edits invalidate it

registry = ToolRegistry([
    Tool("search_docs",
         "Search the company's product and security documentation. Returns the top 3 chunks with doc, "
         "section, last updated date and a relevance score, plus a COVERAGE line. Use this first for every "
         "question, and again with different wording if the results look off topic.",
         {"type": "object",
          "properties": {"query": {"type": "string", "description": "A short natural language search"}},
          "required": ["query"]},
         tools.search_docs),
    Tool("read_doc",
         "Read one full section of a document. Use it after search_docs when a chunk looks "
         "relevant but cut off.",
         {"type": "object",
          "properties": {"name": {"type": "string", "description": "Document name, for example sso_identity"},
                         "section": {"type": "string", "description": "Section heading"}},
          "required": ["name", "section"]},
         tools.read_doc),
    Tool("record_answer",
         "Save your draft answer for one question. Call it exactly once per question. Cite doc and section "
         "for every claim. Set needs_human true if the docs conflict, do not cover it, or the question has a "
         "false premise.",
         {"type": "object",
          "properties": {"question_id": {"type": "string"},
                         "answer": {"type": "string"},
                         "citations": {"type": "array", "items": {"type": "string"},
                                       "description": "Each as 'doc / section'. If sources conflict, "
                                                      "include EVERY conflicting source, old and new."},
                         "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                         "needs_human": {"type": "boolean"},
                         "reason": {"type": "string",
                                    "description": "Why, especially for conflicts and gaps"}},
          "required": ["question_id", "answer", "citations", "confidence", "needs_human", "reason"]},
         tools.record_answer),
    Tool("export_answers",
         "Write all recorded answers to the final answer sheet file. Only call when asked to export.",
         {"type": "object", "properties": {}},
         tools.export_answers, needs_approval=True),
])


def build_input(case: dict) -> str:
    # Only the id and question go to the model. The CSV's category column is a label that would
    # give the answer away, so it is never passed in.
    return f"Question ID: {case['id']}\n<question>{case['input']}</question>"


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Do you encrypt customer data at rest?"
    r = run_agent(SYSTEM, build_input({"id": "q_adhoc", "input": q}), registry,
                  stop_after_tool=STOP_AFTER_TOOL)
    print("\nANSWER:", r["answer"])
    print("TOOLS:", r["tools_called"], "STEPS:", r["steps"], "COST: $", r["cost_usd"])
