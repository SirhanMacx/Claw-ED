"""Claw-ED conversational agent -- LLM with tool use.

The agent loop:
  1. Send message + tool definitions to LLM
  2. If LLM returns tool_calls -> execute tools, feed results back
  3. If LLM returns text -> return it
  4. Repeat (max 5 iterations to prevent infinite loops)

Works with Anthropic (native tool use), OpenAI (function calling),
and Ollama (when model supports tools, falls back to prompt-based).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from clawed.models import AppConfig, LLMProvider
from clawed.tools import TOOL_DEFINITIONS, execute_tool


def _is_oauth_token(api_key: str) -> bool:
    """Detect if a token is an OAuth token vs a regular API key.

    Delegates to the shared helper in clawed.config for consistent
    detection across all modules.
    """
    from clawed.config import is_anthropic_oauth_token
    return is_anthropic_oauth_token(api_key)


def _anthropic_headers(api_key: str) -> dict[str, str]:
    """Build Anthropic API headers, auto-detecting OAuth vs regular API keys.

    OAuth tokens need Bearer auth + Claude Code identity headers.
    Regular API keys (sk-ant-api*) use x-api-key.
    """
    if _is_oauth_token(api_key):
        return {
            "authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": (
                "interleaved-thinking-2025-05-14,"
                "claude-code-20250219,oauth-2025-04-20"
            ),
            "user-agent": "claude-cli/1.0.0 (external, cli)",
            "x-app": "cli",
            "content-type": "application/json",
        }
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

logger = logging.getLogger(__name__)

_MAX_TOOL_ITERATIONS = 5


async def run_agent(
    message: str,
    system: str,
    teacher_id: str = "",
    config: AppConfig | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
) -> str:
    """Run the conversational agent with tool use.

    Returns the final text response after any tool calls are resolved.
    """
    config = config or AppConfig.load()

    messages: list[dict[str, Any]] = list(conversation_history or [])
    messages.append({"role": "user", "content": message})

    for _iteration in range(_MAX_TOOL_ITERATIONS):
        if config.provider in (LLMProvider.ANTHROPIC, LLMProvider.OPENAI):
            response = await _call_with_native_tools(messages, system, config)
        else:
            response = await _call_with_ollama_tools(messages, system, config)

        if response["type"] == "text":
            return response["content"]

        if response["type"] == "tool_calls":
            tool_calls = response["tool_calls"]

            # Add ONE assistant message containing ALL tool calls
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls,
            })

            # Execute each tool and add its result
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("arguments", {})
                logger.info("Agent calling tool: %s(%s)", tool_name, tool_args)

                result = await execute_tool(tool_name, tool_args, teacher_id)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", tool_name),
                    "content": result,
                })
            continue

    return "I tried to help but hit my iteration limit. Could you rephrase your request?"


async def _call_with_native_tools(
    messages: list[dict[str, Any]], system: str, config: AppConfig
) -> dict[str, Any]:
    """Call Anthropic or OpenAI with native tool support."""
    if config.provider == LLMProvider.ANTHROPIC:
        return await _anthropic_with_tools(messages, system, config)
    else:
        return await _openai_with_tools(messages, system, config)


async def _anthropic_with_tools(
    messages: list[dict[str, Any]], system: str, config: AppConfig
) -> dict[str, Any]:
    """Call Anthropic API with tool use."""

    from clawed.config import get_api_key

    api_key = get_api_key("anthropic")
    if not api_key:
        raise ValueError("No Anthropic API key configured")

    # Convert tool definitions to Anthropic format
    tools = []
    for t in TOOL_DEFINITIONS:
        f = t["function"]
        tools.append({
            "name": f["name"],
            "description": f["description"],
            "input_schema": f["parameters"],
        })

    # Convert messages to Anthropic format
    anthropic_messages: list[dict[str, Any]] = []
    for m in messages:
        if m["role"] == "tool":
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": m["content"],
                }],
            })
        elif m["role"] == "assistant" and m.get("tool_calls"):
            # Single assistant message with ALL tool_use blocks
            content_blocks = []
            for tc in m["tool_calls"]:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", tc["name"]),
                    "name": tc["name"],
                    "input": tc.get("arguments", {}),
                })
            anthropic_messages.append({"role": "assistant", "content": content_blocks})
        elif m.get("content"):
            anthropic_messages.append({"role": m["role"], "content": m["content"]})

    import anthropic as _anthropic

    if _is_oauth_token(api_key):
        sdk_client = _anthropic.Anthropic(
            auth_token=api_key,
            default_headers={"anthropic-beta": "oauth-2025-04-20", "x-app": "cli"},
            max_retries=3,
        )
    else:
        sdk_client = _anthropic.Anthropic(api_key=api_key, max_retries=3)

    msg = sdk_client.messages.create(
        model=config.anthropic_model,
        max_tokens=4096,
        system=system,
        tools=tools,
        messages=anthropic_messages,
    )

    # Collect ALL tool_use blocks and any text
    tool_calls = []
    text_parts = []
    for block in msg.content:
        if block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "name": block.name,
                "arguments": block.input,
            })
        elif block.type == "text" and block.text:
            text_parts.append(block.text)

    if tool_calls:
        return {"type": "tool_calls", "tool_calls": tool_calls}
    if text_parts:
        return {"type": "text", "content": "\n".join(text_parts)}
    return {"type": "text", "content": ""}


async def _openai_with_tools(
    messages: list[dict[str, Any]], system: str, config: AppConfig
) -> dict[str, Any]:
    """Call OpenAI-compatible API with function calling (OpenAI, OpenRouter)."""
    import httpx

    from clawed.config import get_api_key

    # Route to the right provider's API key
    api_key = get_api_key("openrouter") if config.provider == LLMProvider.OPENROUTER else get_api_key("openai")
    if not api_key:
        raise ValueError("No OpenAI API key configured")

    oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "tool":
            oai_messages.append({
                "role": "tool",
                "tool_call_id": m.get("tool_call_id", ""),
                "content": m["content"],
            })
        elif m["role"] == "assistant" and m.get("tool_calls"):
            # Single assistant message with ALL tool calls
            oai_tool_calls = []
            for tc in m["tool_calls"]:
                oai_tool_calls.append({
                    "id": tc.get("id", tc["name"]),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments", {})),
                    },
                })
            oai_messages.append({"role": "assistant", "tool_calls": oai_tool_calls})
        elif m.get("content"):
            oai_messages.append({"role": m["role"], "content": m["content"]})

    # Determine URL and model based on provider
    if config.provider == LLMProvider.OPENROUTER:
        url = f"{getattr(config, 'openrouter_base_url', 'https://openrouter.ai/api/v1').rstrip('/')}/chat/completions"
        model = config.openrouter_model
        extra_headers = {"HTTP-Referer": "https://github.com/SirhanMacx/Claw-ED", "X-Title": "Claw-ED"}
    else:
        url = "https://api.openai.com/v1/chat/completions"
        model = config.openai_model
        extra_headers = {}

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                **extra_headers,
            },
            json={
                "model": model,
                "messages": oai_messages,
                "tools": TOOL_DEFINITIONS,
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    choice = data["choices"][0]
    msg = choice["message"]

    if msg.get("tool_calls"):
        # Collect ALL tool calls
        tool_calls = []
        for tc in msg["tool_calls"]:
            tool_calls.append({
                "id": tc["id"],
                "name": tc["function"]["name"],
                "arguments": json.loads(tc["function"]["arguments"]),
            })
        return {"type": "tool_calls", "tool_calls": tool_calls}

    return {"type": "text", "content": msg.get("content", "")}


async def _call_with_ollama_tools(
    messages: list[dict[str, Any]], system: str, config: AppConfig
) -> dict[str, Any]:
    """Call Ollama with tool support (native if available, prompt-based fallback)."""
    import httpx

    from clawed.config import get_api_key

    base_url = config.ollama_base_url.rstrip("/")
    api_key = config.ollama_api_key or get_api_key("ollama")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Build the URL — normalize trailing slashes, append /v1 exactly once
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    url = f"{base_url}/chat/completions"

    oai_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if m["role"] == "tool":
            oai_messages.append({
                "role": "tool",
                "tool_call_id": m.get("tool_call_id", ""),
                "content": m["content"],
            })
        elif m["role"] == "assistant" and m.get("tool_calls"):
            oai_tool_calls = []
            for tc in m["tool_calls"]:
                oai_tool_calls.append({
                    "id": tc.get("id", tc["name"]),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments", {})),
                    },
                })
            oai_messages.append({"role": "assistant", "tool_calls": oai_tool_calls})
        elif m.get("content"):
            oai_messages.append({"role": m["role"], "content": m["content"]})

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            resp = await client.post(
                url,
                headers=headers,
                json={
                    "model": config.ollama_model,
                    "messages": oai_messages,
                    "tools": TOOL_DEFINITIONS,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]

        if msg.get("tool_calls"):
            tool_calls = []
            for tc in msg["tool_calls"]:
                fn_args = tc["function"]["arguments"]
                tool_calls.append({
                    "id": tc.get("id", tc["function"]["name"]),
                    "name": tc["function"]["name"],
                    "arguments": json.loads(fn_args) if isinstance(fn_args, str) else fn_args,
                })
            return {"type": "tool_calls", "tool_calls": tool_calls}

        return {"type": "text", "content": msg.get("content", "")}

    except Exception as e:
        logger.debug("Ollama tool call failed (%s), falling back to plain chat", e)
        return await _ollama_plain_chat(messages, system, config)


async def _ollama_plain_chat(
    messages: list[dict[str, Any]], system: str, config: AppConfig
) -> dict[str, Any]:
    """Plain Ollama chat without tools (fallback)."""
    from clawed.llm import LLMClient
    from clawed.model_router import route

    routed_config = route("quick_answer", config)
    client = LLMClient(routed_config)

    prompt = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages if m.get("content")
    )
    response = await client.generate(prompt=prompt, system=system, temperature=0.7, max_tokens=800)
    return {"type": "text", "content": response}
