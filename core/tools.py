"""A tool is a normal Python function plus a description Claude can read.
Claude chooses tools using the description alone, so write it like instructions
to a new hire: what it does, when to use it, what the inputs mean."""
from typing import Callable


class Tool:
    def __init__(self, name: str, description: str, input_schema: dict,
                 fn: Callable, needs_approval: bool = False):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.fn = fn
        self.needs_approval = needs_approval

    def to_api(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": self.input_schema}


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        names = [t.name for t in tools]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate tool names in registry")
        self._tools = {t.name: t for t in tools}

    def api_schemas(self) -> list[dict]:
        return [t.to_api() for t in self._tools.values()]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)
