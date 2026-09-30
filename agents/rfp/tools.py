"""The RFP agent's tools. Claude decides WHEN to call them. Code decides what they
return and what they refuse, because facts and rules belong in code, not the model."""
import json
import os

from agents.rfp import settings
from agents.rfp.chunks import load_chunks
from agents.rfp.retriever import Retriever

CONFIDENCE = {"high", "medium", "low"}
ANSWERS: dict[str, dict] = {}     # drafts collected this session, keyed by question id
_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def search_docs(query: str) -> str:
    hits = get_retriever().search(query)
    if not hits:
        return "The document index is empty. Run: python -m agents.rfp.ingest"
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(f"[{i}] {h['doc']} / {h['section']} "
                     f"(updated {h['updated']}, score {h['score']})\n{h['text']}")
    best = hits[0]["score"]
    # The threshold is applied in code, so weak evidence is flagged the same way every time.
    if best < settings.MIN_SCORE:
        lines.append(f"COVERAGE: WEAK. Best score {best} is below {settings.MIN_SCORE}. "
                     "The documents probably do not cover this. Do not answer from these results.")
    else:
        lines.append(f"COVERAGE: OK. Best score {best}.")
    return "\n\n".join(lines)


def read_doc(name: str, section: str) -> str:
    everything = load_chunks(settings.DATA_DIR)
    chunks = [c for c in everything if c.doc == name]
    if not chunks:
        return f"No document named '{name}'. Documents: {sorted({c.doc for c in everything})}"
    for c in chunks:
        if c.section.lower() == section.lower():
            return f"{c.doc} / {c.section} (updated {c.updated})\n{c.text}"
    return f"No section '{section}' in {name}. Sections: {[c.section for c in chunks]}"


def record_answer(question_id: str, answer: str, citations: list[str], confidence: str,
                  needs_human: bool, reason: str) -> str:
    if confidence not in CONFIDENCE:
        raise ValueError(f"confidence must be one of {sorted(CONFIDENCE)}")
    # No source, no claim: a confident answer with nothing cited is rejected.
    if not needs_human and not citations:
        raise ValueError("An answer with needs_human false must cite at least one doc and section.")
    ANSWERS[question_id] = {"question_id": question_id, "answer": answer, "citations": citations,
                            "confidence": confidence, "needs_human": needs_human, "reason": reason}
    return f"Recorded answer for {question_id}."


def export_answers() -> str:
    os.makedirs("runs", exist_ok=True)
    path = "runs/rfp_answers.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(ANSWERS.values()), f, indent=2)
    return f"Wrote {len(ANSWERS)} answers to {path}"
