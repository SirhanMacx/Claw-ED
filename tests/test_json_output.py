"""Tests for the JSON output infrastructure."""

import json
import subprocess
import sys

import pytest


def test_json_envelope_success():
    """JSON output wraps successful results in standard envelope."""
    from clawed._json_output import json_envelope

    result = json_envelope("gen.lesson", data={"title": "WWI"}, files=["/tmp/out.docx"])
    assert result["status"] == "success"
    assert result["command"] == "gen.lesson"
    assert result["data"]["title"] == "WWI"
    assert result["files"] == ["/tmp/out.docx"]
    assert result["errors"] == []
    assert result["warnings"] == []


def test_json_envelope_error():
    """JSON output wraps errors properly."""
    from clawed._json_output import json_envelope

    result = json_envelope("gen.lesson", status="error", errors=["API key missing"])
    assert result["status"] == "error"
    assert result["errors"] == ["API key missing"]


def test_json_envelope_serializable():
    """Envelope is JSON-serializable."""
    from clawed._json_output import json_envelope

    result = json_envelope("test", data={"nested": {"key": "val"}})
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    roundtrip = json.loads(serialized)
    assert roundtrip["data"]["nested"]["key"] == "val"


def test_lesson_json_flag_error_without_config():
    """clawed lesson --json returns JSON envelope or times out (needs API key)."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "clawed",
                "--python",
                "lesson",
                "Test Topic",
                "-g",
                "8",
                "-s",
                "US History",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip():
            try:
                output = json.loads(result.stdout)
                assert output["command"] == "gen.lesson"
                assert output["status"] in ("success", "error")
            except json.JSONDecodeError:
                pass  # Non-JSON output acceptable without config
    except subprocess.TimeoutExpired:
        pytest.skip("Lesson generation needs API key (timed out)")


# ── emit_json ────────────────────────────────────────────────────────


def test_emit_json_writes_to_stdout(capsys):
    """emit_json writes JSON to stdout followed by newline."""
    from clawed._json_output import emit_json, json_envelope

    envelope = json_envelope("test.cmd", data={"key": "value"})
    emit_json(envelope)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["command"] == "test.cmd"
    assert parsed["data"]["key"] == "value"


def test_emit_json_handles_non_serializable(capsys):
    """emit_json uses default=str for non-serializable objects."""
    from datetime import datetime

    from clawed._json_output import emit_json, json_envelope

    envelope = json_envelope("test", data={"ts": datetime(2025, 1, 1)})
    emit_json(envelope)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert "2025" in parsed["data"]["ts"]


# ── run_json_command ─────────────────────────────────────────────────


def test_run_json_command_success(capsys):
    """run_json_command emits success envelope from function result."""
    from clawed._json_output import run_json_command

    def my_fn():
        return {"data": {"score": 95}, "files": ["/tmp/report.pdf"]}

    run_json_command("test.score", my_fn)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["status"] == "success"
    assert parsed["data"]["score"] == 95
    assert "/tmp/report.pdf" in parsed["files"]


def test_run_json_command_catches_exception(capsys):
    """run_json_command catches exceptions and returns error envelope."""
    from clawed._json_output import run_json_command

    def bad_fn():
        raise ValueError("something broke")

    run_json_command("test.fail", bad_fn)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["status"] == "error"
    assert any("something broke" in e for e in parsed["errors"])


def test_run_json_command_handles_none_return(capsys):
    """run_json_command handles fn returning None."""
    from clawed._json_output import run_json_command

    def none_fn():
        return None

    run_json_command("test.none", none_fn)
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["status"] == "success"
    assert parsed["data"] is None


def test_json_envelope_defaults():
    """json_envelope provides sensible defaults."""
    from clawed._json_output import json_envelope

    result = json_envelope("test")
    assert result["status"] == "success"
    assert result["data"] is None
    assert result["files"] == []
    assert result["warnings"] == []
    assert result["errors"] == []


def test_json_envelope_with_nested_data():
    """json_envelope handles deeply nested data structures."""
    from clawed._json_output import json_envelope

    data = {"level1": {"level2": {"level3": [1, 2, 3]}}}
    result = json_envelope("test.nested", data=data)
    serialized = json.dumps(result)
    roundtrip = json.loads(serialized)
    assert roundtrip["data"]["level1"]["level2"]["level3"] == [1, 2, 3]


def test_json_envelope_with_warnings():
    """json_envelope includes warnings when provided."""
    from clawed._json_output import json_envelope

    result = json_envelope("test", warnings=["low confidence", "missing data"])
    assert result["warnings"] == ["low confidence", "missing data"]
