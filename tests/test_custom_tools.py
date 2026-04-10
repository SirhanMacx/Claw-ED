"""Tests for custom YAML prompt-template tools."""

import yaml

from clawed.agent_core.context import AgentContext
from clawed.models import AppConfig


def _make_ctx():
    return AgentContext(
        teacher_id="t1",
        config=AppConfig(),
        teacher_profile={},
        persona=None,
        session_history=[],
        improvement_context="",
    )


class TestYAMLToolParsing:
    def test_load_from_yaml(self, tmp_path):
        from clawed.agent_core.custom_tools import YAMLPromptTool

        yaml_content = {
            "name": "lab_safety",
            "description": "Check lab safety",
            "parameters": {
                "lesson_text": {"type": "string", "description": "Lesson text"},
            },
            "prompt_template": "Check safety: {lesson_text}",
        }
        tool_file = tmp_path / "lab_safety.yml"
        tool_file.write_text(yaml.dump(yaml_content))
        tool = YAMLPromptTool.from_file(tool_file)
        assert tool is not None

    def test_schema(self, tmp_path):
        from clawed.agent_core.custom_tools import YAMLPromptTool

        yaml_content = {
            "name": "vocab_check",
            "description": "Check vocabulary level",
            "parameters": {
                "text": {"type": "string", "description": "Text to check"},
                "grade": {"type": "string", "description": "Grade level"},
            },
            "prompt_template": "Check vocab for grade {grade}: {text}",
        }
        tool_file = tmp_path / "vocab.yml"
        tool_file.write_text(yaml.dump(yaml_content))
        tool = YAMLPromptTool.from_file(tool_file)
        s = tool.schema()
        assert s["function"]["name"] == "vocab_check"
        assert "text" in s["function"]["parameters"]["properties"]
        assert "grade" in s["function"]["parameters"]["properties"]

    def test_invalid_yaml_returns_none(self, tmp_path):
        from clawed.agent_core.custom_tools import YAMLPromptTool

        tool_file = tmp_path / "bad.yml"
        tool_file.write_text("not: valid: yaml: [[[")
        tool = YAMLPromptTool.from_file(tool_file)
        assert tool is None

    def test_missing_required_fields(self, tmp_path):
        from clawed.agent_core.custom_tools import YAMLPromptTool

        tool_file = tmp_path / "incomplete.yml"
        tool_file.write_text(yaml.dump({"name": "incomplete"}))
        tool = YAMLPromptTool.from_file(tool_file)
        assert tool is None


class TestCustomToolDiscovery:
    def test_discover_custom_tools(self, tmp_path):
        from clawed.agent_core.tools.base import ToolRegistry

        # Create a custom tool
        yaml_content = {
            "name": "my_custom_tool",
            "description": "A custom tool",
            "parameters": {"input": {"type": "string", "description": "Input"}},
            "prompt_template": "Process: {input}",
        }
        (tmp_path / "custom.yml").write_text(yaml.dump(yaml_content))

        reg = ToolRegistry()
        reg.discover_custom(tmp_path)
        assert "my_custom_tool" in reg.tool_names()

    def test_discover_skips_broken_yaml(self, tmp_path):
        from clawed.agent_core.tools.base import ToolRegistry

        (tmp_path / "broken.yml").write_text("invalid yaml [[[")
        (tmp_path / "empty.yaml").write_text("")
        reg = ToolRegistry()
        reg.discover_custom(tmp_path)
        assert len(reg.tool_names()) == 0  # nothing loaded, no crash
