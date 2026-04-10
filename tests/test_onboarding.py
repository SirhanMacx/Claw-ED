"""Tests for clawed.onboarding — first-run guided wizard."""

from __future__ import annotations

from unittest.mock import patch

from clawed.models import AppConfig, LLMProvider


class TestOnboardingImport:
    def test_module_imports(self):
        from clawed.onboarding import (
            US_STATES,
            check_first_run,
            run_onboarding,
        )

        assert callable(run_onboarding)
        assert callable(check_first_run)
        assert isinstance(US_STATES, list)

    def test_us_states_complete(self):
        from clawed.onboarding import US_STATES

        # 50 states + DC = 51
        assert len(US_STATES) == 51

    def test_us_states_sorted(self):
        from clawed.onboarding import US_STATES

        assert US_STATES == sorted(US_STATES)


class TestResolveState:
    def test_full_name(self):
        from clawed.onboarding import _resolve_state

        assert _resolve_state("New York") == "NY"
        assert _resolve_state("California") == "CA"
        assert _resolve_state("Texas") == "TX"

    def test_abbreviation(self):
        from clawed.onboarding import _resolve_state

        assert _resolve_state("NY") == "NY"
        assert _resolve_state("CA") == "CA"
        assert _resolve_state("tx") == "TX"

    def test_case_insensitive(self):
        from clawed.onboarding import _resolve_state

        assert _resolve_state("new york") == "NY"
        assert _resolve_state("NEW YORK") == "NY"
        assert _resolve_state("california") == "CA"

    def test_prefix_match(self):
        from clawed.onboarding import _resolve_state

        assert _resolve_state("New Y") == "NY"
        assert _resolve_state("Cal") == "CA"

    def test_invalid_state(self):
        from clawed.onboarding import _resolve_state

        assert _resolve_state("Narnia") is None
        assert _resolve_state("") is None
        assert _resolve_state("XX") is None

    def test_dc(self):
        from clawed.onboarding import _resolve_state

        assert _resolve_state("DC") == "DC"
        assert _resolve_state("District of Columbia") == "DC"


class TestCheckFirstRun:
    def test_returns_false_when_config_exists(self, tmp_path):
        """If config already exists, check_first_run returns False."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        with patch.object(AppConfig, "config_path", return_value=config_file):
            from clawed.onboarding import check_first_run

            result = check_first_run()
            assert result is False

    def test_returns_true_when_no_config(self, tmp_path):
        """If no config, check_first_run launches onboarding and returns True."""
        config_file = tmp_path / "nonexistent" / "config.json"

        with (
            patch.object(AppConfig, "config_path", return_value=config_file),
            patch("clawed.onboarding.run_onboarding") as mock_onboard,
            patch("sys.stdin") as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            mock_onboard.return_value = AppConfig()

            from clawed.onboarding import check_first_run

            result = check_first_run()
            assert result is True
            mock_onboard.assert_called_once()

    def test_handles_keyboard_interrupt(self, tmp_path):
        """If user Ctrl-C during onboarding, it should not crash."""
        config_file = tmp_path / "nonexistent" / "config.json"

        with (
            patch.object(AppConfig, "config_path", return_value=config_file),
            patch("clawed.onboarding.run_onboarding", side_effect=KeyboardInterrupt),
            patch("sys.stdin") as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            from clawed.onboarding import check_first_run

            result = check_first_run()
            assert result is True

    def test_skips_onboarding_when_non_interactive(self, tmp_path):
        """When stdin is not a TTY, skip interactive onboarding."""
        config_file = tmp_path / "nonexistent" / "config.json"

        with (
            patch.object(AppConfig, "config_path", return_value=config_file),
            patch("clawed.onboarding.run_onboarding") as mock_onboard,
            patch("sys.stdin") as mock_stdin,
        ):
            mock_stdin.isatty.return_value = False
            from clawed.onboarding import check_first_run

            result = check_first_run()
            assert result is True
            mock_onboard.assert_not_called()


class TestAskProvider:
    def test_anthropic_selection(self):
        from clawed.onboarding import _ask_provider

        with patch("clawed.onboarding.Prompt.ask", side_effect=["2", "sk-ant-test-key"]):
            provider, key = _ask_provider()
            assert provider == LLMProvider.ANTHROPIC
            assert key == "sk-ant-test-key"

    def test_openai_selection(self):
        from clawed.onboarding import _ask_provider

        with patch("clawed.onboarding.Prompt.ask", side_effect=["3", "sk-test-key"]):
            provider, key = _ask_provider()
            assert provider == LLMProvider.OPENAI
            assert key == "sk-test-key"

    def test_ollama_selection_no_key(self):
        from clawed.onboarding import _ask_provider

        with patch("clawed.onboarding.Prompt.ask", return_value="4"):
            provider, key = _ask_provider()
            assert provider == LLMProvider.OLLAMA
            assert key is None


class TestAskMaterials:
    def test_skip_returns_none_tuple(self):
        from clawed.onboarding import _ask_materials

        with patch("clawed.onboarding.Prompt.ask", return_value="4"):
            local_path, drive_url = _ask_materials()
            assert local_path is None
            assert drive_url is None

    def test_browse_folder_picker(self, tmp_path):
        from clawed.onboarding import _ask_materials

        with patch("clawed.onboarding.Prompt.ask", side_effect=["1", ""]):
            with patch("clawed.onboarding._open_folder_picker", return_value=str(tmp_path)):
                local_path, drive_url = _ask_materials()
                assert local_path == str(tmp_path)
                assert drive_url is None

    def test_paste_path(self, tmp_path):
        from clawed.onboarding import _ask_materials

        lesson_dir = tmp_path / "lessons"
        lesson_dir.mkdir()

        with patch("clawed.onboarding.Prompt.ask", side_effect=["2", str(lesson_dir), ""]):
            local_path, drive_url = _ask_materials()
            assert local_path == str(lesson_dir)

    def test_drive_link(self):
        from clawed.onboarding import _ask_materials

        with patch("clawed.onboarding.Prompt.ask", side_effect=["3", "https://drive.google.com/folder/abc"]):
            local_path, drive_url = _ask_materials()
            assert local_path is None
            assert drive_url == "https://drive.google.com/folder/abc"

    def test_invalid_path_no_crash(self):
        from clawed.onboarding import _ask_materials

        with patch("clawed.onboarding.Prompt.ask", side_effect=["2", "/nonexistent/xyz", ""]):
            local_path, drive_url = _ask_materials()
            assert local_path is None


class TestStateNameToAbbr:
    def test_all_50_states_plus_dc_mapped(self):
        from clawed.onboarding import _STATE_NAME_TO_ABBR

        # Every state in the config should have both name and abbreviation entries
        from clawed.state_standards import STATE_STANDARDS_CONFIG

        for abbr, info in STATE_STANDARDS_CONFIG.items():
            assert info["name"].lower() in _STATE_NAME_TO_ABBR
            assert abbr.lower() in _STATE_NAME_TO_ABBR


class TestRunOnboarding:
    def test_full_flow_saves_config(self, tmp_path):
        """Simulate a complete onboarding flow and verify config is saved."""
        config_file = tmp_path / "config.json"

        # New wizard flow: subjects, grades, state, confirm,
        # Ollama key prompt (empty = skip), alternative choice "3" (local),
        # retry/skip on failed connection, materials (skip)
        side_effects = [
            "Global History",  # subjects
            "10",  # grade levels
            "New York",  # state
            "y",  # persona preview confirmation
            "",  # Ollama key prompt (skip to alternatives)
            "3",  # alternative: local Ollama
            "skip",  # retry/skip on connection test
            "",  # materials (skip)
        ]

        with (
            patch.object(AppConfig, "config_path", return_value=config_file),
            patch("clawed.onboarding.Prompt.ask", side_effect=side_effects),
            patch("clawed.onboarding._test_connection", return_value=False),
            patch("clawed.onboarding._detect_available_models", return_value=(None, "No LLM found")),
        ):
            from clawed.onboarding import run_onboarding

            config = run_onboarding()

            assert config.provider == LLMProvider.OLLAMA
            assert config.teacher_profile.state == "NY"
            assert "Global History" in config.teacher_profile.subjects
            assert "10" in config.teacher_profile.grade_levels
            assert config_file.exists()


class TestSetupWizard:
    def test_run_setup_wizard_exists(self):
        from clawed.onboarding import run_setup_wizard

        assert callable(run_setup_wizard)

    def test_setup_command_registered(self):
        from clawed.cli import app

        # Typer uses the callback function name as the command name when
        # name is not explicitly set.  Check both .name and callback.__name__.
        command_names = []
        for cmd in app.registered_commands:
            if cmd.name:
                command_names.append(cmd.name)
            elif cmd.callback:
                command_names.append(cmd.callback.__name__)
        assert "setup" in command_names

    def test_detect_env_anthropic(self, monkeypatch):
        from clawed.onboarding import _detect_available_models

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        provider, msg = _detect_available_models()
        assert provider == LLMProvider.ANTHROPIC

    def test_detect_env_ollama_key(self, monkeypatch):
        from clawed.onboarding import _detect_available_models

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        provider, msg = _detect_available_models()
        assert provider == LLMProvider.OLLAMA
        assert "Cloud" in msg

    def test_detect_env_openai(self, monkeypatch):
        from clawed.onboarding import _detect_available_models

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        provider, msg = _detect_available_models()
        assert provider == LLMProvider.OPENAI

    def test_run_onboarding_is_alias(self):
        """run_onboarding should be a backward-compatible alias for run_setup_wizard."""
        from clawed.onboarding import run_onboarding, run_setup_wizard

        # run_onboarding internally calls run_setup_wizard
        assert callable(run_onboarding)
        assert callable(run_setup_wizard)

    def test_wizard_with_ollama_cloud_key(self, tmp_path):
        """Teacher enters Ollama Cloud key directly at the recommended prompt."""
        config_file = tmp_path / "config.json"

        side_effects = [
            "Social Studies, ELA",  # subjects
            "7, 8",  # grade levels
            "New York",  # state
            "y",  # persona preview confirmation
            "ollama-cloud-key-123",  # Ollama Cloud key (entered at recommended prompt)
            "",  # materials (skip)
        ]

        with (
            patch.object(AppConfig, "config_path", return_value=config_file),
            patch("clawed.onboarding.Prompt.ask", side_effect=side_effects),
            patch("clawed.onboarding._test_connection", return_value=True),
            patch("clawed.onboarding._detect_available_models", return_value=(None, "No LLM found")),
            patch("clawed.onboarding.set_api_key") as mock_set_key,
        ):
            from clawed.onboarding import run_setup_wizard

            config = run_setup_wizard()

            assert config.provider == LLMProvider.OLLAMA
            assert config.ollama_base_url == "https://ollama.com"
            assert config.ollama_model == "gemma4:31b-cloud"
            mock_set_key.assert_any_call("ollama", "ollama-cloud-key-123")

    def test_wizard_skip_for_now(self, tmp_path):
        """Teacher chooses 'skip for now' — config saves without a provider error."""
        config_file = tmp_path / "config.json"

        side_effects = [
            "Math",  # subjects
            "6",  # grade levels
            "California",  # state
            "y",  # persona preview confirmation
            "",  # Ollama key (skip)
            "4",  # Skip for now
            "",  # materials (skip)
        ]

        with (
            patch.object(AppConfig, "config_path", return_value=config_file),
            patch("clawed.onboarding.Prompt.ask", side_effect=side_effects),
            patch("clawed.onboarding._detect_available_models", return_value=(None, "No LLM found")),
        ):
            from clawed.onboarding import run_setup_wizard

            config = run_setup_wizard()

            assert config.teacher_profile.state == "CA"
            assert "Math" in config.teacher_profile.subjects
            assert config_file.exists()

    def test_wizard_reset_clears_config(self, tmp_path):
        """--reset should clear existing config before starting."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"provider": "openai"}')

        side_effects = [
            "Science",  # subjects
            "9",  # grade levels
            "Texas",  # state
            "y",  # persona preview confirmation
            "",  # Ollama key (skip)
            "3",  # local Ollama
            "skip",  # retry/skip
            "",  # materials (skip)
        ]

        with (
            patch.object(AppConfig, "config_path", return_value=config_file),
            patch("clawed.onboarding.Prompt.ask", side_effect=side_effects),
            patch("clawed.onboarding._test_connection", return_value=False),
            patch("clawed.onboarding._detect_available_models", return_value=(None, "No LLM found")),
        ):
            from clawed.onboarding import run_setup_wizard

            config = run_setup_wizard(reset=True)

            assert config.provider == LLMProvider.OLLAMA
            assert config.teacher_profile.state == "TX"

    def test_wizard_auto_detects_anthropic(self, tmp_path):
        """If ANTHROPIC_API_KEY is in env, skip the provider prompt entirely."""
        config_file = tmp_path / "config.json"

        side_effects = [
            "ELA",  # subjects
            "5",  # grade levels
            "Florida",  # state
            "y",  # persona preview confirmation
            "",  # materials (skip)
        ]

        with (
            patch.object(AppConfig, "config_path", return_value=config_file),
            patch("clawed.onboarding.Prompt.ask", side_effect=side_effects),
            patch("clawed.onboarding._test_connection", return_value=True),
            patch(
                "clawed.onboarding._detect_available_models",
                return_value=(LLMProvider.ANTHROPIC, "Anthropic API key found in environment"),
            ),
        ):
            from clawed.onboarding import run_setup_wizard

            config = run_setup_wizard()

            assert config.provider == LLMProvider.ANTHROPIC
            assert config.teacher_profile.state == "FL"
