"""Tests for clawed.cli_chat — terminal chat interface."""

from __future__ import annotations


class TestCliChatImport:
    def test_module_imports(self):
        from clawed.cli_chat import main, run_chat

        assert callable(main)
        assert callable(run_chat)

    def test_welcome_message_content(self):
        from clawed.cli_chat import _WELCOME

        assert "Claw-ED" in _WELCOME
        assert "/quit" in _WELCOME
        assert "/status" in _WELCOME
        assert "/clear" in _WELCOME


class TestChatCommand:
    def test_chat_command_registered(self):
        from typer.testing import CliRunner

        from clawed.cli import app

        runner = CliRunner()
        # --help should list chat command
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "interactive chat" in result.output.lower() or "chat session" in result.output.lower()

    def test_chat_accepts_id_option(self):
        from typer.testing import CliRunner

        from clawed.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["chat", "--help"])
        # Strip ANSI escape codes before checking
        import re

        clean = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "--id" in clean
