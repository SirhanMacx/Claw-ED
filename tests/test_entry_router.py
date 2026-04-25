"""Tests for the entry point router."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clawed._entry_router import (
    _find_bundled_cli_js,
    _find_daemon_entry,
    _show_node_notice,
    main,
)

# -- _find_bundled_cli_js --------------------------------------------------


def test_find_bundled_cli_js_returns_path_or_none():
    """Returns a cli.js path if found, or None in test environment."""
    result = _find_bundled_cli_js()
    if result is not None:
        assert Path(result).name == "cli.js"


def test_find_bundled_cli_js_returns_none_when_nothing_exists(tmp_path):
    """Returns None when no cli.js exists anywhere."""
    pkg_dir = tmp_path / "clawed"
    pkg_dir.mkdir()
    fake_file = pkg_dir / "_entry_router.py"
    fake_file.write_text("# placeholder")

    import clawed._entry_router as mod
    original_file = mod.__file__

    try:
        mod.__file__ = str(fake_file)
        result = _find_bundled_cli_js()
        assert result is None
    finally:
        mod.__file__ = original_file


def test_find_bundled_cli_js_finds_bundled(tmp_path):
    """Returns bundled _cli_bundle/cli.js when it exists."""
    pkg_dir = tmp_path / "clawed"
    pkg_dir.mkdir()
    fake_file = pkg_dir / "_entry_router.py"
    fake_file.write_text("# placeholder")
    cli_js = pkg_dir / "_cli_bundle" / "cli.js"
    cli_js.parent.mkdir(parents=True)
    cli_js.write_text("// bundle")

    import clawed._entry_router as mod
    original_file = mod.__file__

    try:
        mod.__file__ = str(fake_file)
        result = _find_bundled_cli_js()
        assert result is not None
        assert result == str(cli_js)
    finally:
        mod.__file__ = original_file


# -- _find_daemon_entry ----------------------------------------------------


def test_find_daemon_entry_returns_none_when_nothing_exists(tmp_path):
    """Returns None when no daemon entry exists."""
    pkg_dir = tmp_path / "clawed"
    pkg_dir.mkdir()
    fake_file = pkg_dir / "_entry_router.py"
    fake_file.write_text("# placeholder")

    import clawed._entry_router as mod
    original_file = mod.__file__

    try:
        mod.__file__ = str(fake_file)
        result = _find_daemon_entry()
        assert result is None
    finally:
        mod.__file__ = original_file


# -- _show_node_notice -----------------------------------------------------


def test_show_node_notice_branded(capsys):
    """Node notice shows branded Claw-ED startup with version."""
    _show_node_notice()

    captured = capsys.readouterr()
    assert "C L A W - E D" in captured.out
    assert "Your AI co-teacher" in captured.out


# -- main ------------------------------------------------------------------


def test_main_routes_daemon_commands():
    """'daemon' arg routes to _handle_daemon."""
    with patch("sys.argv", ["clawed", "daemon", "start"]):
        with patch("clawed._entry_router._handle_daemon") as mock_daemon:
            main()
            mock_daemon.assert_called_once_with(["start"])


def test_main_python_flag_routes_to_python_cli():
    """--python flag routes to _run_python_cli."""
    with patch("sys.argv", ["clawed", "--python", "--version"]):
        with patch("clawed._entry_router._run_python_cli") as mock_py:
            main()
            mock_py.assert_called_once()


def test_main_version_uses_python_package_version(capsys):
    """--version should not depend on the bundled Node CLI version."""
    with patch("sys.argv", ["clawed", "--version"]):
        with patch("subprocess.run") as mock_run:
            main()

    captured = capsys.readouterr()
    assert "4.25.2026 (Claw-ED)" in captured.out
    mock_run.assert_not_called()


def test_main_no_node_falls_back_to_python():
    """When Node.js is absent, falls back to Python CLI."""
    with patch("sys.argv", ["clawed", "lesson", "test"]):
        with patch("shutil.which", return_value=None):
            with patch("clawed._entry_router._run_python_cli") as mock_py:
                main()
                mock_py.assert_called_once()


def test_main_node_available_with_cli_js():
    """When Node.js and cli.js exist, interactive mode runs via Node subprocess."""
    with patch("sys.argv", ["clawed", "-p", "hello"]):
        with patch("shutil.which", return_value="/usr/bin/node"):
            with patch(
                "clawed._entry_router._find_bundled_cli_js",
                return_value="/fake/cli.js",
            ):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 0
                    call_args = mock_run.call_args[0][0]
                    assert call_args[0] == "/usr/bin/node"
                    assert call_args[1] == "/fake/cli.js"


def test_python_commands_route_to_python():
    """Known subcommands (lesson, debug, kb, etc.) always route to Python CLI."""
    with patch("sys.argv", ["clawed", "debug"]):
        with patch("shutil.which", return_value="/usr/bin/node"):
            with patch(
                "clawed._entry_router._find_bundled_cli_js",
                return_value="/fake/cli.js",
            ):
                with patch("clawed._entry_router._run_python_cli") as mock_py:
                    main()
                    mock_py.assert_called_once()
