"""Hello agent: the smallest possible agent. Use it to learn the core and to
smoke test changes. Run: python -m agents.hello.agent"""
from core.agent import run_agent
from core.tools import Tool, ToolRegistry

DOCS = {
    "sso": "SSO is supported via SAML 2.0 and OIDC on the Enterprise plan only.",
    "encryption": "Data is encrypted at rest with AES-256 and in transit with TLS 1.2 or higher.",
    "retention": "Customer data is retained for 90 days after contract end, then deleted.",
}
NOTES: list[str] = []


def search_docs(query: str) -> str:
    hits = [f"[{k}] {v}" for k, v in DOCS.items() if k in query.lower()]
    return "\n".join(hits) if hits else "No matching docs found."


def save_note(text: str) -> str:
    NOTES.append(text)
    return f"Saved note #{len(NOTES)}"


registry = ToolRegistry([
    Tool("search_docs",
         "Search product documentation by a single keyword such as sso, encryption, or retention. "
         "Use this before answering any product question.",
         {"type": "object",
          "properties": {"query": {"type": "string", "description": "One keyword"}},
          "required": ["query"]},
         search_docs),
    Tool("save_note", "Save a follow up note for the sales team. Use only when something is unclear.",
         {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
         save_note, needs_approval=True),
])

SYSTEM = ("You answer customer security questions using only the docs returned by your tools. "
          "If the docs do not cover the question, say you do not know. Never guess.")


def build_input(case: dict) -> str:
    return case["input"]


if __name__ == "__main__":
    r = run_agent(SYSTEM, "Do you support SSO and how long do you keep data?", registry)
    print("\nANSWER:", r["answer"])
    print("STEPS:", r["steps"], "COST: $", r["cost_usd"])
