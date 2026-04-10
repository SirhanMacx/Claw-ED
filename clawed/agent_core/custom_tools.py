"""Custom teacher tools -- YAML prompt-template tools loaded from ~/.eduagent/tools/."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"name", "description", "parameters", "prompt_template"}


class YAMLPromptTool:
    """A tool defined by a YAML file with a prompt template."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        prompt_template: str,
    ) -> None:
        self._name = name
        self._description = description
        self._parameters = parameters
        self._prompt_template = prompt_template

    @classmethod
    def from_file(cls, path: Path) -> YAMLPromptTool | None:
        """Load a tool from a YAML file. Returns None if invalid."""
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            if not _REQUIRED_FIELDS.issubset(data.keys()):
                logger.warning(
                    "Custom tool %s missing fields: %s",
                    path.name,
                    _REQUIRED_FIELDS - data.keys(),
                )
                return None
            return cls(
                name=data["name"],
                description=data["description"],
                parameters=data["parameters"],
                prompt_template=data["prompt_template"],
            )
        except Exception as e:
            logger.warning("Failed to load custom tool %s: %s", path.name, e)
            return None

    def schema(self) -> dict[str, Any]:
        """Return the JSON Schema definition the LLM sees."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param_name, param_def in self._parameters.items():
            properties[param_name] = {
                "type": param_def.get("type", "string"),
                "description": param_def.get("description", ""),
            }
            if param_def.get("required", True):
                required.append(param_name)
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        """Fill the prompt template and send to LLM."""
        try:
            filled = self._prompt_template.format(**params)
        except KeyError as e:
            return ToolResult(text=f"Missing parameter: {e}")

        # Send filled prompt to LLM for processing
        try:
            from clawed.llm import LLMClient

            client = LLMClient(context.config)
            response = await client.generate(filled)
            return ToolResult(
                text=response,
                side_effects=[f"Custom tool '{self._name}' executed"],
            )
        except Exception as e:
            return ToolResult(text=f"Custom tool failed: {e}")
