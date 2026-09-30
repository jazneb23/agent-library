"""The agent loop. Everything else in this repo exists to feed or guard this.

Ask Claude what to do. If it wants a tool, run the tool (behind the approval
gate if needed), hand the result back, and ask again. Stop when Claude answers
without asking for a tool, or when max_steps is hit."""
import uuid

from core import config
from core.approval import ask_approval
from core.logger import log_event
from core.tools import ToolRegistry


def _truncate(text: str) -> str:
    limit = config.MAX_TOOL_OUTPUT_CHARS
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated {len(text) - limit} characters]"


def run_agent(system: str, user_message: str, registry: ToolRegistry, *,
              client=None, max_steps: int | None = None, stop_after_tool: str | None = None) -> dict:
    """stop_after_tool: end the run as soon as this tool succeeds and use its "answer"
    input as the final answer. It saves the last model call, which would only repeat it."""
    client = client or config.get_client()
    max_steps = max_steps or config.MAX_STEPS
    run_id = uuid.uuid4().hex[:8]
    messages = [{"role": "user", "content": user_message}]
    tokens_in = tokens_out = 0
    tools_called: list[str] = []
    tool_events: list[dict] = []

    log_event(run_id, "run_start", model=config.MODEL, user_message=user_message)

    def finish(answer: str, steps: int, reason: str) -> dict:
        cost = config.cost_usd(tokens_in, tokens_out)
        log_event(run_id, "run_end", reason=reason, steps=steps,
                  tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)
        return {"run_id": run_id, "answer": answer, "steps": steps, "cost_usd": cost,
                "tokens_in": tokens_in, "tokens_out": tokens_out, "stop_reason": reason,
                "tools_called": tools_called, "tool_events": tool_events}

    for step in range(1, max_steps + 1):
        # 1. Ask Claude what to do next. It remembers nothing, so we resend everything.
        response = client.messages.create(
            model=config.MODEL, max_tokens=config.MAX_TOKENS, system=system,
            tools=registry.api_schemas(), messages=messages)
        tokens_in += response.usage.input_tokens
        tokens_out += response.usage.output_tokens

        # 2. Save Claude's reply into the conversation.
        messages.append({"role": "assistant", "content": response.content})

        # 3. No tool requested means Claude is done.
        if response.stop_reason != "tool_use":
            answer = "".join(b.text for b in response.content if b.type == "text")
            return finish(answer, step, "end_turn")

        # 4. Run every tool Claude asked for.
        results = []
        stop_input = None
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool = registry.get(block.name)
            tools_called.append(block.name)
            log_event(run_id, "tool_call", tool=block.name, input=block.input)

            if tool is None:
                output, is_error = f"Unknown tool: {block.name}", True
            elif tool.needs_approval and not ask_approval(block.name, block.input):
                output, is_error = "A human denied this action. Do not retry it.", True
                log_event(run_id, "approval_denied", tool=block.name)
            else:
                try:
                    output, is_error = str(tool.fn(**block.input)), False
                except Exception as e:  # return errors to Claude so it can recover
                    output, is_error = f"Tool error: {e}", True

            output = _truncate(output)
            log_event(run_id, "tool_result", tool=block.name, is_error=is_error,
                      output=output[:500])
            tool_events.append({"tool": block.name, "input": block.input,
                                "output": output, "is_error": is_error})
            if stop_after_tool and block.name == stop_after_tool and not is_error:
                stop_input = block.input
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": output, "is_error": is_error})

        # The stop tool worked, so the run is complete. Skip the extra model call.
        if stop_input is not None:
            return finish(str(stop_input.get("answer", "")), step, "stop_tool")

        # 5. Feed the results back and go around again.
        messages.append({"role": "user", "content": results})

    return finish("Stopped: hit max steps.", max_steps, "max_steps")
