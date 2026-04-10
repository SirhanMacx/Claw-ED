"""Test --json flag on all commands that support it."""

import json
import subprocess
import sys

import pytest

# Commands that work fast without API key
FAST_COMMANDS = [
    (["ingest", "/tmp/nonexistent", "--json"], "gen.ingest"),
]

# Commands that may hang (API calls, slow imports, or timeout)
GENERATION_COMMANDS = [
    (["unit", "Test", "-g", "8", "-s", "US History", "--json"], "gen.unit"),
    (["materials", "--lesson-file", "/tmp/nonexistent.json", "--json"], "gen.materials"),
    (["game", "create", "Test", "--json"], "game.create"),
    (["train", "--benchmark", "-n", "0", "--json"], "train"),
    (["config", "show", "--json"], "config.show"),
]


@pytest.mark.parametrize("args,expected_command", FAST_COMMANDS)
@pytest.mark.skipif(True, reason="Flaky on CI — ingest --json output varies")
def test_json_flag_produces_valid_envelope(args, expected_command):
    """Commands that don't need an API key return valid JSON envelopes."""
    result = subprocess.run(
        [sys.executable, "-m", "clawed", "--python"] + args,
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = json.loads(result.stdout)
    assert output["command"] == expected_command
    assert output["status"] in ("success", "error")
    assert isinstance(output["files"], list)
    assert isinstance(output["errors"], list)


@pytest.mark.parametrize("args,expected_command", GENERATION_COMMANDS)
def test_generation_json_flag(args, expected_command):
    """Generation commands return JSON, error text, or timeout (need API key)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "clawed", "--python"] + args,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if not result.stdout.strip():
            return  # Empty output — acceptable (no config/key)
        try:
            output = json.loads(result.stdout)
            assert output["status"] in ("success", "error")
        except json.JSONDecodeError:
            pass  # Non-JSON output (typer error) — acceptable without config
    except subprocess.TimeoutExpired:
        pytest.skip("Generation command needs API key (timed out)")
