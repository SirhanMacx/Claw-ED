"""Tool: switch_model — change provider, model, or tier routing."""
from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class SwitchModelTool:
    """Switch providers, models, or configure tier routing."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "switch_model",
                "description": (
                    "Switch AI provider, model, or configure tier routing. "
                    "Actions: current, list, switch, switch_provider, "
                    "set_tier, list_providers. "
                    "Use set_tier to route fast/deep tasks to different "
                    "providers (e.g., Ollama for quick answers, Claude for "
                    "lesson generation)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "current", "list", "switch",
                                "switch_provider", "set_tier",
                                "list_providers",
                            ],
                            "description": (
                                "current=show active, list=show models, "
                                "switch=change model, switch_provider="
                                "change provider, set_tier=route tier to "
                                "provider, list_providers=show configured"
                            ),
                        },
                        "model_name": {
                            "type": "string",
                            "description": "Model name (for switch action)",
                        },
                        "provider": {
                            "type": "string",
                            "description": (
                                "Provider name: ollama, anthropic, openai, "
                                "google, openrouter"
                            ),
                        },
                        "tier": {
                            "type": "string",
                            "enum": ["fast", "work", "deep"],
                            "description": "Tier for set_tier action",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext,
    ) -> ToolResult:
        action = params.get("action", "current")
        config = context.config

        if action == "current":
            return self._current(config)
        if action == "list":
            return self._list_models(config)
        if action == "switch":
            return self._switch_model(params, config)
        if action == "switch_provider":
            return self._switch_provider(params)
        if action == "set_tier":
            return self._set_tier(params)
        if action == "list_providers":
            return self._list_providers()
        return ToolResult(text=f"Unknown action: {action}")

    def _current(self, config) -> ToolResult:
        provider = config.provider.value
        model_map = {
            "ollama": config.ollama_model,
            "anthropic": config.anthropic_model,
            "openai": config.openai_model,
            "google": config.google_model,
            "openrouter": config.openrouter_model,
        }
        model = model_map.get(provider, "unknown")
        tiers = config.tier_providers or {}
        parts = [f"Provider: {provider}", f"Model: {model}"]
        if tiers:
            parts.append("Tier routing:")
            for tier, prov in tiers.items():
                parts.append(f"  {tier} → {prov}")
        return ToolResult(
            text="\n".join(parts),
            data={"model": model, "provider": provider},
        )

    def _list_models(self, config) -> ToolResult:
        """List models from all configured providers."""
        from clawed.model_discovery import list_all_models

        all_models = list_all_models(config)
        if not all_models:
            return ToolResult(text="No models found.")

        current_provider = config.provider.value
        model_map = {
            "ollama": config.ollama_model,
            "anthropic": config.anthropic_model,
            "openai": config.openai_model,
            "google": config.google_model,
            "openrouter": config.openrouter_model,
        }
        current_model = model_map.get(current_provider, "")

        lines = []
        for provider, models in all_models.items():
            active = " (active)" if provider == current_provider else ""
            lines.append(f"\n**{provider.title()}{active}:**")
            for m in models[:10]:
                name = m.get("name") or m.get("id", "?")
                marker = " ✓" if name == current_model else ""
                lines.append(f"  {name}{marker}")

        return ToolResult(
            text="\n".join(lines),
            data={"providers": list(all_models.keys())},
        )

    def _switch_model(self, params, config) -> ToolResult:
        model_name = params.get("model_name", "")
        if not model_name:
            return ToolResult(text="Specify a model_name to switch to.")

        from clawed.models import AppConfig
        cfg = AppConfig.load()
        field_map = {
            "ollama": "ollama_model",
            "anthropic": "anthropic_model",
            "openai": "openai_model",
            "google": "google_model",
            "openrouter": "openrouter_model",
        }
        field = field_map.get(cfg.provider.value, "ollama_model")
        setattr(cfg, field, model_name)
        cfg.save()
        return ToolResult(
            text=f"Switched to {model_name}.",
            side_effects=[f"Model → {model_name}"],
        )

    def _switch_provider(self, params) -> ToolResult:
        provider = params.get("provider", "")
        if not provider:
            return ToolResult(text="Specify a provider name.")

        from clawed.config import get_api_key
        from clawed.models import AppConfig, LLMProvider

        # Verify key exists
        key = get_api_key(provider)
        if not key and provider not in ("ollama",):
            return ToolResult(
                text=f"No API key found for {provider}. "
                f"Set one with: clawed setup",
            )

        try:
            cfg = AppConfig.load()
            cfg.provider = LLMProvider(provider)
            cfg.save()
            return ToolResult(
                text=f"Switched to {provider}.",
                side_effects=[f"Provider → {provider}"],
            )
        except ValueError:
            return ToolResult(
                text=f"Unknown provider: {provider}. "
                "Options: ollama, anthropic, openai, google, openrouter",
            )

    def _set_tier(self, params) -> ToolResult:
        tier = params.get("tier", "")
        provider = params.get("provider", "")
        if not tier or not provider:
            return ToolResult(
                text="Specify both tier and provider. "
                "Example: tier=deep, provider=anthropic",
            )

        from clawed.models import AppConfig
        cfg = AppConfig.load()
        tiers = cfg.tier_providers or {}
        tiers[tier] = provider
        cfg.tier_providers = tiers
        cfg.save()
        return ToolResult(
            text=f"Tier '{tier}' now routes to {provider}.",
            side_effects=[f"Tier {tier} → {provider}"],
        )

    def _list_providers(self) -> ToolResult:
        from clawed.config import get_api_key

        providers = [
            "ollama", "anthropic", "openai", "google", "openrouter",
        ]
        lines = ["Configured providers:"]
        for p in providers:
            key = get_api_key(p)
            status = "configured" if key else "no key"
            lines.append(f"  {p}: {status}")
        return ToolResult(text="\n".join(lines))
