"""Jev adapter tests. The offline ones use a fake client. The live contract test makes
real calls (pennies) and only runs when RUN_LIVE=1:  RUN_LIVE=1 python -m pytest tests/test_jev_contract.py"""
import os
from types import SimpleNamespace as NS

import pytest

from core import decisions
from core.decisions import Choice, Noul, Score
from core.decisions_jev import JevDecider

QUESTIONS = {
    "tone": Choice("What is the customer's tone?", ["calm", "frustrated", "angry"]),
    "urgency": Score("How urgent is this?", ["can wait", "this week", "today"]),
    "billing": Noul("Is this ticket about billing?"),
}


class FakeJev:
    """Mimics typesafe_sdk's response shape, so the adapter is tested without the network."""
    def __init__(self, choice="angry", score=1.4, noul=0.9):
        self.resp = NS(
            usage=NS(input_tokens=500, output_tokens=0),
            choices={"tone": NS(choice=choice, confidence=0.8, probabilities={"calm": .1, "frustrated": .1, "angry": .8})},
            scores={"urgency": NS(score=score, confidence=0.6, probabilities={0: .2, 1: .6, 2: .2})},
            nouls={"billing": NS(noul=noul)})

    def system_one(self, state, questions):
        self.seen = (state, questions)
        return self.resp


def test_adapter_maps_all_three_types_and_records_cost():
    decisions.reset_stats()
    out = JevDecider(client=FakeJev()).decide("I was charged twice!", QUESTIONS)
    assert out["tone"].value == "angry" and out["tone"].confidence == 0.8
    assert out["urgency"].value == 1.4 and out["urgency"].kind == "score"
    assert out["billing"].value == 0.9 and out["billing"].confidence is None   # Noul has no confidence
    assert decisions.STATS["calls"] == 1
    assert decisions.STATS["usd"] == pytest.approx(500 * 0.042 / 1_000_000)


def test_adapter_sends_the_sdk_question_shape():
    fake = FakeJev()
    JevDecider(client=fake).decide("text", QUESTIONS)
    state, qs = fake.seen
    assert state == {"text": "text"}
    assert set(qs["tone"].criteria) == {"calm", "frustrated", "angry"}
    assert list(qs["urgency"].criteria) == ["can wait", "this week", "today"]


def test_adapter_validates_even_typed_output():
    with pytest.raises(ValueError):
        JevDecider(client=FakeJev(choice="furious")).decide("x", QUESTIONS)   # not an allowed option
    with pytest.raises(ValueError):
        JevDecider(client=FakeJev(score=7.0)).decide("x", QUESTIONS)          # outside the scale


@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="live call, set RUN_LIVE=1 to run")
def test_live_contract_one_call_per_primitive():
    decisions.reset_stats()
    out = JevDecider().decide("I was charged twice. Please fix this ASAP.", QUESTIONS)
    assert out["tone"].value in QUESTIONS["tone"].options and 0 <= out["tone"].confidence <= 1
    assert 0 <= out["urgency"].value <= 2
    assert 0 <= out["billing"].value <= 1 and out["billing"].confidence is None
    print("\nLIVE:", {k: (d.value, d.confidence) for k, d in out.items()}, decisions.STATS)
