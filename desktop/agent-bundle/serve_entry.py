"""PyInstaller entry point for the bundled clawed agent sidecar.

The Tauri app ships this as Contents/Resources/clawed-agent/clawed-agent
and invokes it exactly like the `clawed` CLI:

    clawed-agent serve --host 127.0.0.1 --port 8000 --skip-setup

Hard rules baked in (docs/product/HANDOFF.md):
- PYTHON_KEYRING_BACKEND=null — the agent must NEVER touch the login
  keychain, no matter how the binary is launched.
- Defaults to `serve` when invoked with no arguments, so double-clicking
  the binary still yields a healthy loopback agent.

The auth boundary (EDUAGENT_LOCAL_AUTH_BYPASS) is intentionally NOT baked
in — the supervisor that spawns the process decides that.
"""
from __future__ import annotations

import multiprocessing
import os
import sys


def run() -> None:
    # The keychain rule — set BEFORE any clawed import can load keyring.
    os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    # Pin the data dir: clawed.database falls back to a RELATIVE
    # ./clawed_data when EDUAGENT_DATA_DIR is unset, which explodes when a
    # GUI app spawns us with cwd=/ (PermissionError on startup).
    home = os.path.expanduser("~")
    os.environ.setdefault("EDUAGENT_DATA_DIR", os.path.join(home, ".eduagent"))
    # A writable, predictable cwd for any other relative-path stragglers.
    try:
        os.chdir(home)
    except OSError:
        pass

    if len(sys.argv) == 1:
        sys.argv += ["serve", "--host", "127.0.0.1", "--skip-setup"]

    # Route through the same entry as the `clawed` console script.
    sys.argv[0] = "clawed"
    from clawed._entry_router import main

    main()


if __name__ == "__main__":
    # PyInstaller + multiprocessing: without this, a spawned child
    # re-executes the bundle and starts a second server.
    multiprocessing.freeze_support()
    run()
