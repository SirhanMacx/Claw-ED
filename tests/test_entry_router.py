"""Every entry path uses the owned Python runtime."""
from unittest.mock import AsyncMock, patch

import pytest

from clawed._entry_router import main
from clawed.gateway_response import GatewayResponse


@pytest.mark.parametrize("args", [[], ["lesson", "test"], ["--help"], ["--python", "--help"]])
def test_routes_to_python_without_spawning_node(args):
    with patch("sys.argv", ["clawed", *args]), patch("clawed._entry_router._run_python_cli") as cli:
        with patch("subprocess.run") as process:
            main()
            cli.assert_called_once()
            process.assert_not_called()


def test_version(capsys):
    from clawed import __version__
    with patch("sys.argv", ["clawed", "--version"]):
        main()
    assert __version__ in capsys.readouterr().out


def test_print_uses_gateway_policy(capsys):
    with patch("sys.argv", ["clawed", "-p", "hello"]), patch("clawed.agent_core.core.Gateway") as gateway:
        gateway.return_value.handle = AsyncMock(return_value=GatewayResponse(text="done"))
        main()
        assert gateway.return_value.handle.await_args.args[0] == "hello"
    assert "done" in capsys.readouterr().out
