"""Jev backend for the decision layer (TypeSafe's System One model).

This file is an ADAPTER. The rest of the repo speaks our own Choice, Score and Noul
types and gets Decision objects back. This file translates to the TypeSafe SDK and
back, so swapping Claude for Jev (or a cascade of both) never touches an agent.

Facts from the official docs (docs.typesafe.ai):
  Choice and Score answers carry confidence and probabilities.
  Noul answers carry ONE probability and no confidence field.
  Price: $0.042 per million input tokens, output is free."""
from __future__ import annotations

import os
import time

from core.decisions import Choice, Decision, Score, record_stats, validate

# Published price per million input tokens. Kept in an environment variable so a price change
# is a config edit, not a code edit.
PRICE_IN_PER_M = float(os.getenv("JEV_PRICE_IN_PER_M", "0.042"))


def _to_sdk(questions: dict) -> dict:
    """Our question types to the SDK's. The SDK names the options 'criteria'."""
    import typesafe_sdk as ts
    out = {}
    for name, q in questions.items():
        if isinstance(q, Choice):
            out[name] = ts.Choice(instructions=q.instructions, criteria={o: None for o in q.options})
        elif isinstance(q, Score):
            out[name] = ts.Score(instructions=q.instructions, criteria=list(q.levels))
        else:
            out[name] = ts.Noul(instructions=q.instructions)
    return out


class JevDecider:
    name = "jev"

    def __init__(self, client=None):
        self._client = client

    def _get_client(self):
        if self._client is None:
            from typesafe_sdk import TypeSafeClient
            self._client = TypeSafeClient()   # reads TYPESAFE_API_KEY from the environment
        return self._client

    def decide(self, state: str, questions: dict) -> dict[str, Decision]:
        start = time.time()
        # The state is data to read. Wrapping it in a dict keeps it clearly separate from the questions.
        resp = self._get_client().system_one(state={"text": state}, questions=_to_sdk(questions))

        tokens = getattr(resp.usage, "input_tokens", None)
        if tokens is None:   # the API may not report it, so fall back to a rough 4 characters per token
            tokens = (len(state) + sum(len(q.instructions) for q in questions.values())) // 4
        record_stats(tokens * PRICE_IN_PER_M / 1_000_000, time.time() - start)

        out: dict[str, Decision] = {}
        for name, q in questions.items():
            if isinstance(q, Choice):
                a = resp.choices[name]
                out[name] = Decision("choice", a.choice, a.confidence, self.name, dict(a.probabilities))
            elif isinstance(q, Score):
                a = resp.scores[name]
                out[name] = Decision("score", a.score, a.confidence, self.name, dict(a.probabilities))
            else:
                out[name] = Decision("noul", resp.nouls[name].noul, None, self.name)
        validate(questions, out)   # typed does not mean correct, so check anyway
        return out
