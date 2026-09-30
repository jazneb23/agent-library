"""Human in the loop gate. Any tool marked needs_approval pauses here.

APPROVAL_MODE (environment variable):
  prompt        ask a human in the terminal (default)
  auto_approve  approve everything (evals, since they cannot wait for a human)
  auto_deny     deny everything (use it to prove nothing gets written)

Swap this function for a Slack message or a web button later. The agent loop
does not change, which is the point of isolating it here."""
import os


def ask_approval(tool_name: str, tool_input: dict) -> bool:
    mode = os.getenv("APPROVAL_MODE", "prompt")
    if mode == "auto_approve":
        return True
    if mode == "auto_deny":
        return False
    print("\n--- APPROVAL REQUIRED ---")
    print(f"Tool:  {tool_name}")
    print(f"Input: {tool_input}")
    try:
        return input("Approve? (y/n): ").strip().lower() == "y"
    except EOFError:  # no human available, so fail safe
        return False
