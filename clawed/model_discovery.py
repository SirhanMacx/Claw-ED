"""Dynamic model discovery for all providers.

Lists available models from Ollama Cloud, OpenRouter, and other
providers via their APIs. Used by the /models command and the
switch_model agent tool.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def list_ollama_models(
    base_url: str = "http://localhost:11434",
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """List available Ollama models (local or cloud).

    Returns: [{"name": "gemma4:31b-cloud", "size": ..., "family": ...}]
    """
    import httpx

    base = base_url.rstrip("/")
    headers = {}
    if api_key and api_key not in ("ollama-local", "ollama", "local"):
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = httpx.get(
            f"{base}/api/tags", headers=headers, timeout=10,
        )
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            return [
                {
                    "name": m.get("name", ""),
                    "size": m.get("size", 0),
                    "family": m.get("details", {}).get("family", ""),
                    "parameter_size": m.get("details", {}).get(
                        "parameter_size", ""
                    ),
                }
                for m in models
                if m.get("name")
            ]
    except Exception as e:
        logger.debug("Ollama model listing failed: %s", e)

    return []


def list_openrouter_models(
    api_key: str | None = None,
    free_only: bool = False,
) -> list[dict[str, Any]]:
    """List available OpenRouter models.

    The /models endpoint is public (no auth needed for listing).
    Set free_only=True to filter for models with zero cost.
    """
    import httpx

    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers, timeout=15,
        )
        if resp.status_code != 200:
            return []

        models = resp.json().get("data", [])
        result = []
        for m in models:
            pricing = m.get("pricing", {})
            prompt_cost = pricing.get("prompt", "0")
            completion_cost = pricing.get("completion", "0")
            is_free = str(prompt_cost) == "0" and str(completion_cost) == "0"

            if free_only and not is_free:
                continue

            result.append({
                "id": m.get("id", ""),
                "name": m.get("name", m.get("id", "")),
                "context_length": m.get("context_length", 0),
                "free": is_free,
                "prompt_cost": prompt_cost,
                "completion_cost": completion_cost,
            })

        return result

    except Exception as e:
        logger.debug("OpenRouter model listing failed: %s", e)
        return []


# Known models for providers without listing APIs
ANTHROPIC_MODELS = [
    {"name": "claude-sonnet-4-6", "tier": "work"},
    {"name": "claude-opus-4-6", "tier": "deep"},
    {"name": "claude-haiku-3.5", "tier": "fast"},
]

OPENAI_MODELS = [
    {"name": "gpt-4.1", "tier": "deep"},
    {"name": "gpt-4.1-mini", "tier": "fast"},
    {"name": "gpt-4.1-nano", "tier": "fast"},
    {"name": "o3", "tier": "deep"},
    {"name": "o4-mini", "tier": "work"},
]

GOOGLE_MODELS = [
    {"name": "gemini-2.5-flash", "tier": "fast"},
    {"name": "gemini-2.5-pro", "tier": "deep"},
]

# OpenRouter curated models (paid first, then free options)
OPENROUTER_FREE_MODELS = [
    {"id": "zhipu/glm-5.1", "name": "GLM 5.1", "free": False, "tools": True},
    {"id": "qwen/qwen3.6-plus:free", "name": "Qwen 3.6 Plus", "free": True},
    {"id": "nvidia/nemotron-3-super-120b-a12b:free", "name": "Nemotron 3 Super 120B", "free": True},
    {"id": "google/gemma-3-27b-it:free", "name": "Gemma 3 27B", "free": True},
    {"id": "deepseek/deepseek-chat-v3-0324:free", "name": "DeepSeek V3", "free": True},
    {"id": "meta-llama/llama-4-scout:free", "name": "Llama 4 Scout", "free": True},
    {"id": "mistralai/mistral-small-3.2-24b-instruct:free", "name": "Mistral Small 3.2", "free": True},
]


def list_all_models(config: Any = None) -> dict[str, list[dict[str, Any]]]:
    """List models from all configured providers.

    Returns: {"ollama": [...], "openrouter": [...], "anthropic": [...], ...}
    """
    from clawed.config import get_api_key

    result: dict[str, list[dict[str, Any]]] = {}

    # Ollama (dynamic discovery)
    if config:
        ollama_key = get_api_key("ollama")
        base = getattr(config, "ollama_base_url", "http://localhost:11434")
        models = list_ollama_models(base, ollama_key)
        if models:
            result["ollama"] = models

    # OpenRouter (dynamic discovery + free fallback)
    or_key = get_api_key("openrouter")
    or_models = list_openrouter_models(or_key, free_only=(not or_key))
    if or_models:
        result["openrouter"] = or_models[:30]
    elif or_key:
        # API failed but key exists — show known free models
        result["openrouter"] = OPENROUTER_FREE_MODELS
    else:
        # No key — still show free models (they work without a key)
        result["openrouter"] = OPENROUTER_FREE_MODELS

    # Static lists for API-key providers
    if get_api_key("anthropic"):
        result["anthropic"] = ANTHROPIC_MODELS
    if get_api_key("openai"):
        result["openai"] = OPENAI_MODELS
    if get_api_key("google"):
        result["google"] = GOOGLE_MODELS

    # Always show Ollama Cloud catalog — merge with API results
    ollama_catalog = result.get("ollama", [])
    catalog_names = {m.get("name", "") for m in ollama_catalog}
    for m in OLLAMA_CLOUD_MODELS:
        if m["name"] not in catalog_names:
            ollama_catalog.append(m)
    result["ollama"] = ollama_catalog

    return result


# Full Ollama Cloud catalog (updated April 2026)
# Source: https://ollama.com/search?c=cloud
OLLAMA_CLOUD_MODELS = [
    # ── Recommended (tool use, proven quality) ──
    {"name": "gemma4:31b-cloud", "tools": True, "tier": "deep"},
    {"name": "gemma4:26b-cloud", "tools": True, "tier": "work"},
    {"name": "deepseek-v3.2:cloud", "tools": True, "tier": "deep"},
    {"name": "qwen3.5:cloud", "tools": True, "tier": "fast"},
    {"name": "qwen3-coder-next:cloud", "tools": True, "tier": "work"},
    {"name": "minimax-m2.7:cloud", "tools": True, "tier": "work"},
    {"name": "minimax-m2.5:cloud", "tools": True, "tier": "work"},
    {"name": "minimax-m2:cloud", "tools": True, "tier": "fast"},
    # ── Large / specialized ──
    {"name": "nemotron-3-super:120b-cloud", "tools": True, "tier": "deep"},
    {"name": "nemotron-3-nano:30b-cloud", "tools": True, "tier": "work"},
    {"name": "nemotron-3-nano:4b-cloud", "tools": True, "tier": "fast"},
    {"name": "devstral-2:123b-cloud", "tools": True, "tier": "deep"},
    {"name": "devstral-small-2:24b-cloud", "tools": True, "tier": "work"},
    {"name": "glm-5.1:cloud", "tools": True, "tier": "deep"},
    {"name": "glm-5:cloud", "tools": True, "tier": "deep"},
    {"name": "glm-4.7:cloud", "tools": True, "tier": "work"},
    {"name": "kimi-k2.5:cloud", "tools": True, "tier": "deep"},
    {"name": "qwen3-next:80b-cloud", "tools": True, "tier": "deep"},
    {"name": "qwen3-vl:cloud", "tools": True, "tier": "work"},
    {"name": "ministral-3:14b-cloud", "tools": True, "tier": "work"},
    {"name": "ministral-3:8b-cloud", "tools": True, "tier": "fast"},
    {"name": "ministral-3:3b-cloud", "tools": True, "tier": "fast"},
    {"name": "rnj-1:8b-cloud", "tools": True, "tier": "fast"},
    {"name": "gemini-3-flash-preview:cloud", "tools": True, "tier": "fast"},
    {"name": "cogito-2.1:671b-cloud", "tools": False, "tier": "deep"},
]
