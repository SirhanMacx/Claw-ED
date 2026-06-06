# Claw-ED Desktop — Packaging Roadmap

> Positioning: **"Claude Code for teachers."** The terminal CLI is the power
> tool; the desktop app is the friendly front door. The heavy engine stays in
> Python. The desktop layer only *wraps and launches* it — calm, one‑click, and
> trustworthy for a non‑technical teacher.

This document tracks how we get from "a teacher has to use a terminal" to "a
teacher double‑clicks an app." It is intentionally incremental: each stage ships
something usable.

- **Engine of record:** `clawed app` → `uvicorn` serving
  `clawed.api.server:app` on `127.0.0.1:8000`
  (`clawed/commands/bot.py`). Health probe: `GET /api/health` (no auth, no DB/LLM
  calls — `clawed/api/routes/settings.py`).
- **Non‑goals:** the desktop app never reimplements generation, never exposes a
  terminal or arbitrary command execution, and never adds telemetry. It is a
  launcher and status surface, nothing more.

---

## Stage 0 — Menu‑bar MVP ✅ (this scaffold)

A SwiftUI `MenuBarExtra` app under `mac-app/`. Builds and runs with
`swift build` / `swift run` (no Xcode required).

Delivered:

- [x] Menu‑bar‑only app (no Dock icon; `.accessory` activation + `LSUIElement`
      documented for the bundle).
- [x] **Start** — launches the documented invocation: `clawed app` (preferred),
      falling back to `python3 -c "…from clawed._entry_router import main; main()"`
      when `clawed` isn't on PATH. Launcher path is configurable in Settings.
- [x] **Health polling** of `GET /api/health` → green/yellow/red status dot.
- [x] **Open** — opens `http://127.0.0.1:8000` in the default browser (auto‑opens
      once when the server first becomes healthy; toggleable).
- [x] **Local + LAN URLs** with copy buttons, and a **CoreImage QR code** of the
      LAN URL for phone access on the same Wi‑Fi.
- [x] **Stop** + clean teardown of the child process on Quit / app exit.
- [x] Read‑only "Activity" log tail (not an interactive terminal).
- [x] No telemetry; localhost‑only by default; no command field in the UI.

Known limitation carried into Stage 2: the LAN URL/QR are shown for convenience,
but `clawed app` binds to `127.0.0.1`, so phones can't actually connect until an
explicit LAN opt‑in exists (Stage 2, "Phone access").

---

## Stage 1 — Signed & notarized `.app`

Goal: a teacher downloads one file, double‑clicks, and it opens with **no
Gatekeeper warning**. (Step‑by‑step commands live in `mac-app/README.md`.)

Tasks:

- [ ] **Bundle** — produce `ClawED Menu Bar.app` wrapping the
      `swift build -c release` binary, with a complete `Info.plist`
      (`CFBundleIdentifier` `app.macxlabs.clawed.menubar`, `LSUIElement = true`,
      `LSMinimumSystemVersion = 14.0`, version strings, copyright).
- [ ] **App icon** — design an `AppIcon.icns` consistent with the Ed mascot /
      MacxLabs brand (`docs/ed-mascot.png` as reference). Provide all required
      sizes (16–1024). Note: a menu‑bar `MenuBarExtra` label can also use a
      template (monochrome) image for the bar glyph; ship one for crispness.
- [ ] **Decide the build host** — keep SwiftPM for CI/no‑Xcode builds *and/or*
      add a thin Xcode "App" target (same sources) for the easiest signed
      bundle. Document whichever is canonical.
- [ ] **Codesign** with a Developer ID Application cert + hardened runtime
      (`codesign --options runtime --timestamp`).
- [ ] **Notarize + staple** via `notarytool` and `stapler`.
- [ ] **Verify** a clean download: `spctl --assess --type execute` → `accepted`.
- [ ] **Distribute** — GitHub Release asset and/or a signed `.dmg`; link from the
      Claw-ED README and the MacxLabs site.
- [ ] **Versioning** — align with the repo's date‑based scheme (e.g. the README
      badge `v5.x.2026`); stamp `CFBundleShortVersionString` to match.

Open question to resolve here:

- **Sandboxing.** Developer ID + hardened runtime (no sandbox) is sufficient and
  is the recommended path, because the app *spawns an external interpreter*,
  which the App Sandbox heavily restricts. If we ever pursue the Mac App Store,
  spawning `python3`/`clawed` won't be permitted — that would force bundling a
  Python runtime (see Stage 3). For Developer ID distribution, **do not
  sandbox**.

---

## Stage 2 — Quality‑of‑life: auto‑start, phone access, robustness

Tasks:

- [ ] **Login‑item auto‑start (opt‑in).** Use `SMAppService.mainApp` (macOS 13+)
      to register the app as a login item, behind a Settings toggle
      ("Start Claw-ED automatically when I log in"). Show real registration
      status; handle the "requires user approval in System Settings > General >
      Login Items" state gracefully. (Avoid the deprecated
      `SMLoginItemSetEnabled` helper‑bundle approach.)
- [ ] **Optional auto‑launch the server on app start** — separate toggle from the
      login item: "When Claw-ED opens, start the server automatically."
- [ ] **Phone access opt‑in (LAN).** A clearly‑labeled, off‑by‑default toggle
      "Allow phones on my Wi‑Fi to connect." When on, launch the server bound to
      `0.0.0.0` (the existing `serve`/landing commands already accept a host and
      warn when it isn't loopback) with a visible in‑app warning and a reminder
      that this exposes Claw-ED to the local network. Keep the default private.
      Only then does the QR code actually connect.
- [ ] **Port‑in‑use handling.** Detect `EADDRINUSE` (already‑running server or a
      conflict) and surface a friendly message + "Open existing" affordance;
      optionally auto‑pick the next free port.
- [ ] **"Already running" detection on launch.** If `/api/health` answers before
      we start anything, adopt that state (show running, enable Open) instead of
      trying to spawn a duplicate.
- [ ] **First‑run / not‑installed guidance.** If neither `clawed` nor `python3`
      resolves, show a calm onboarding card with the exact `pip install clawed`
      step and a "Choose…" button — no dead ends.
- [ ] **Crash/exit surfacing.** Already shows non‑zero exit; add a one‑click
      "Copy log" and a "Restart" button.

---

## Stage 3 — (Optional / later) Zero‑Python install

Only if user research shows `pip install clawed` is too much friction for the
target teacher. Heavier; evaluate before committing.

Options, roughly in order of effort:

- [ ] **Bundle a Python runtime + Claw-ED** inside the `.app` (e.g. a relocatable
      `python-build-standalone` interpreter + a frozen `clawed` install) so the
      teacher needs *nothing* preinstalled. Pros: true double‑click. Cons: large
      bundle, signing every embedded dylib, update story for the engine.
- [ ] **PyInstaller/py2app the server** into a single helper binary the menu‑bar
      app launches. Similar tradeoffs; revisit `clawed/_cli_bundle` packaging
      that already exists in the repo.
- [ ] **Auto‑update** — Sparkle (with EdDSA‑signed appcast) for the Swift app;
      define how the embedded engine updates in lockstep.

---

## Guardrails (apply to every stage)

- **No terminal, no arbitrary commands.** The UI only ever starts/stops the
  known `clawed app` server and opens the browser. Launch arguments are
  constructed in code, never from free‑form user input.
- **Localhost by default.** LAN exposure is always an explicit, clearly‑labeled,
  off‑by‑default opt‑in.
- **No telemetry.** Consistent with `docs/PRIVACY_MODEL.md` ("No third‑party
  analytics").
- **Don't touch the Python surface.** The desktop app lives entirely under
  `mac-app/`; it is not in the Python CI and must not modify Python, templates,
  or config.
- **Match the existing health/port contract.** If the server's bind host, port,
  or health route change in `clawed/`, update `mac-app` constants
  (`AppEnvironment.swift`) and `LaunchPlan.swift` to match.
