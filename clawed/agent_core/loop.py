"""Agent tool-use loop — the core reasoning engine.

Migrated from clawed/agent.py. Supports any LLM that implements
the generate(messages, tools, system) interface.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import ToolRegistry
from clawed.gateway_response import GatewayResponse

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITERATIONS = 20


class LLMInterface(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
    ) -> dict[str, Any]: ...


async def run_agent_loop(
    *,
    message: str,
    system: str,
    context: AgentContext,
    llm: LLMInterface,
    registry: ToolRegistry,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    conversation_history: list[dict[str, Any]] | None = None,
) -> GatewayResponse:
    """Run the agent tool-use loop until the LLM produces a text response
    or the safety iteration limit is reached.

    Args:
        message: The user's input message.
        system: System prompt for the LLM.
        context: The AgentContext passed to every tool execution.
        llm: Any object implementing the LLMInterface protocol.
        registry: ToolRegistry containing available tools.
        max_iterations: Safety limit to prevent infinite loops.
        conversation_history: Optional prior conversation messages.

    Returns:
        A GatewayResponse with the agent's final text and any files
        produced by tool calls.
    """
    messages: list[dict[str, Any]] = list(conversation_history or [])
    messages.append({"role": "user", "content": message})

    all_files: list[Any] = []
    all_side_effects: list[str] = []
    tool_schemas = registry.schemas() or None

    for _iteration in range(max_iterations):
        response = await llm.generate(
            messages=messages, tools=tool_schemas, system=system,
        )

        if response["type"] == "text":
            return GatewayResponse(text=response["content"], files=all_files)

        if response["type"] == "tool_calls":
            tool_calls = response["tool_calls"]

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                name = tc["name"]
                args = tc.get("arguments", {})
                logger.info("Agent calling tool: %s(%s)", name, args)

                context.emit_event("tool_start", {
                    "tool_name": name,
                    "params": {
                        k: (v if isinstance(v, str) and len(v) <= 400
                            else (v[:400] + "…" if isinstance(v, str) else repr(v)[:400]))
                        for k, v in args.items()
                    },
                })

                result: ToolResult = await registry.execute(name, args, context)

                all_files.extend(result.files)
                all_side_effects.extend(result.side_effects)

                context.emit_event("tool_end", {
                    "tool_name": name,
                    "ok": not result.text.startswith(("ERROR:", "BLOCKED:")),
                    "summary": (result.text or "")[:600],
                    "files": [str(f) for f in result.files],
                })

                # Convert ToolResult content to string for the message
                content = result.text
                if not content and result.data:
                    content = json.dumps(result.data)
                if not content:
                    content = "(no output)"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", name),
                    "content": content,
                })
            continue

    # Export guarantee: nudge if generation tools ran without a subsequent
    # export_document call — the teacher likely expects a downloadable file.
    generation_tools = frozenset({
        "generate_lesson", "generate_lesson_bundle", "generate_unit",
        "generate_assessment", "generate_materials", "generate_game",
        "generate_animation", "generate_simulation",
    })
    called_tools = {
        m["tool_calls"][idx]["name"]
        for m in messages if m.get("tool_calls")
        for idx in range(len(m["tool_calls"]))
    }
    generated = bool(called_tools & generation_tools)
    exported = "export_document" in called_tools
    nudge = (
        "\n\nIt looks like I generated content but didn't export it yet. "
        "Would you like me to export it as a PDF, DOCX, or PPTX?"
        if generated and not exported else ""
    )

    # Safety limit reached
    return GatewayResponse(
        text=(
            "I've been working on this for a while. "
            "Here's what I have so far — want me to continue?"
            f"{nudge}"
        ),
        files=all_files,
    )
