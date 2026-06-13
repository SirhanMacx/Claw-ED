# Claw-ED for Mac (desktop/)

The native Mac app: a **Tauri 2** shell (real window, dock icon, menus — not a
browser) rendering the shared **"Calm Studio"** web UI (`ui/`, framework-free).
It is the Mac harness around the clawed Python agent: local sidecar supervision,
Skills gallery, Workspace artifacts, approvals, iPhone pairing, and admin
readiness export.

See `docs/product/REBUILD_DIRECTION.md` for the product direction and
`docs/product/design/clawed-agent-mockup.html` for the design source of truth.
For district pilots, start with `docs/product/DISTRICT_ROLLOUT.md` and
`docs/product/TRUST_AND_SECURITY.md`. For public/provider language, use
`docs/product/AGENT_HARNESS.md`.

## Run it

```bash
# one-time
cd desktop && npm install            # Tauri CLI
# rust toolchain: curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal

# build the .app (ad-hoc signed, no keychain)
npx tauri build
open src-tauri/target/release/bundle/macos/Claw-ED.app

# project-level build/run entrypoint used by Codex
../script/build_and_run.sh --verify

# IT/pilot readiness checks against the live local agent
./scripts/preflight.sh

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

The app first looks for the PyInstaller sidecar bundled at
`Claw-ED.app/Contents/Resources/agent/clawed-agent/clawed-agent`. Dev fallbacks
exist so local checkouts still run without rebuilding the bundle.

## District readiness

- Settings includes **Export readiness report**, which writes
  `~/.eduagent/workspace/clawed-readiness-report.md` without printing secrets.
- The app is bring-your-own-provider. The harness and sidecar are local; if the
  teacher chooses OpenRouter, Ollama Cloud, Anthropic, OpenAI, Google, or another
  cloud provider, prompts/context are sent to that provider. Local Ollama keeps
  model calls on the Mac.
- The Pair iPhone screen renders a QR code with the token hidden inside it; the
  token is not displayed as text.
- `scripts/preflight.sh` checks live health, provider connection, tool registry
  breadth, `run_command` risk classification, pairing token presence, local
  signing state, and notarization state.
- Broad installation outside this developer Mac still needs the
  `scripts/sign_and_notarize.sh` Developer ID/notary flow.
