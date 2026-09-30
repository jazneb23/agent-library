"""Central settings. Every value can be overridden with an environment variable
so you can change behavior without editing code (for example a cheaper model
while iterating: AGENT_MODEL=claude-haiku-4-5-20251001)."""
import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-5-5")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", MODEL)
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))  # circuit breaker on the loop
MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "2000"))
MAX_TOOL_OUTPUT_CHARS = 8000  # cap what a tool can push into the context window

# Price per million tokens. Check the Anthropic pricing page and update.
PRICE_IN_PER_M = float(os.getenv("PRICE_IN_PER_M", "3.0"))
PRICE_OUT_PER_M = float(os.getenv("PRICE_OUT_PER_M", "15.0"))

LOG_PATH = os.getenv("AGENT_LOG_PATH", "runs/log.jsonl")


def get_client():
    """Create the API client lazily, so importing this module (and running unit
    tests) never requires an API key."""
    import anthropic

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is missing. Copy .env.example to .env and add your key.")
    return anthropic.Anthropic()


def cost_usd(tokens_in: int, tokens_out: int) -> float:
    return round((tokens_in * PRICE_IN_PER_M + tokens_out * PRICE_OUT_PER_M) / 1_000_000, 5)
