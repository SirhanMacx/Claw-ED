# Claw-ED for Mac (desktop/)

The native Mac app: a **Tauri 2** shell (real window, dock icon, menus — not a
browser) rendering the shared **"Calm Studio"** web UI (`ui/`, framework-free),
with the clawed Python agent supervised as a **local sidecar** on loopback.

See `docs/product/REBUILD_DIRECTION.md` for the product direction and
`docs/product/design/clawed-agent-mockup.html` for the design source of truth.

## Run it

```bash
# one-time
cd desktop && npm install            # Tauri CLI
# rust toolchain: curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal

# build the .app (ad-hoc signed, no keychain)
npx tauri build
open src-tauri/target/release/bundle/macos/Claw-ED.app

# or dev mode with live UI reload
npx tauri dev
```

## How the sidecar works (src-tauri/src/sidecar.rs)

1. On launch the app probes `GET http://127.0.0.1:8000/api/health`.
   - If a healthy agent already answers (e.g. the `com.macxlabs.clawed-agent`
     launchd service), the app **adopts** it — no second process, no port fight.
   - Otherwise it **spawns** one: `$CLAWED_LAUNCHER` → `clawed` on PATH →
     `python3` module fallback (run from `$CLAWED_REPO`, default
     `~/Projects/Claw-ED`, so dev checkouts work without pip install).
2. A supervisor loop re-probes health every 2s, restarts a dead child
   (budgeted), and emits `sidecar-status` events to the UI.
3. The UI **also** polls `/api/health` itself — the status pill reflects real
   HTTP health, never "the process started" (the old menu-bar status lied).
4. Spawned children always get `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`
   (the keychain rule) and die with the app (RunEvent::Exit + SIGTERM handler).

Env knobs: `CLAWED_PORT` (default 8000) · `CLAWED_LAUNCHER` · `CLAWED_REPO`.

PyInstaller bundling of the agent (no system python needed) is milestone M3.
