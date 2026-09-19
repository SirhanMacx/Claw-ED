"""Request parameters shared by generation and agent adapters.

Model IDs stay user configurable. These narrowly scoped compatibility rules
prevent unsupported sampling parameters on current reasoning models.
"""
from __future__ import annotations


def sampling_parameters(model: str, temperature: float) -> dict[str, float]:
    name = model.rsplit("/", 1)[-1]
    if name.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4", "claude-fable-", "claude-mythos-",
                        "claude-sonnet-5", "claude-opus-5")):
        return {}
    return {"temperature": temperature}


def output_parameters(model: str, max_tokens: int) -> dict[str, int]:
    name = model.rsplit("/", 1)[-1]
    key = "max_completion_tokens" if name.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4")) else "max_tokens"
    return {key: max_tokens}
