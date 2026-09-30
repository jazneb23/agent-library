"""A fake Anthropic client so tests run offline, free, and deterministically."""
from types import SimpleNamespace as NS


def text_response(text: str, tin: int = 10, tout: int = 5):
    return NS(content=[NS(type="text", text=text)], stop_reason="end_turn",
              usage=NS(input_tokens=tin, output_tokens=tout))


def tool_response(name: str, tool_input: dict, tool_id: str = "tu_1", tin: int = 10, tout: int = 5):
    return NS(content=[NS(type="tool_use", id=tool_id, name=name, input=tool_input)],
              stop_reason="tool_use", usage=NS(input_tokens=tin, output_tokens=tout))


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)
