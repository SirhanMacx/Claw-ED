# Claw-ED Menu Bar (macOS)

> The friendly desktop launcher for Claw-ED — "Claude Code for teachers."

A small, calm macOS **menu-bar app** that makes Claw-ED one‑click for
non‑technical teachers. The heavy engine stays in Python; this app only
**wraps and launches** it.

What it does:

- Lives in the **menu bar** (no Dock icon).
- **Start Claw-ED** — launches the local server as a child process using the
  documented `clawed app` invocation.
- **Health dot** — polls `http://127.0.0.1:8000/api/health` and shows green
  when the app is up.
- **Open Claw-ED** — opens `http://127.0.0.1:8000` in your default browser.
- Shows the **local URL** and **LAN URL**, plus a **QR code** of the LAN URL so
  a teacher can open Claw-ED on their phone (same Wi‑Fi).
- **Stop** — terminates the server; also stops cleanly when you Quit.

Design principles: warm and trustworthy, **no telemetry**, **localhost‑only by
default**. The UI **never** exposes a terminal or arbitrary command execution —
it can only start/stop the known Claw-ED server and open the browser.

---

## Prerequisites

1. **macOS 14 (Sonoma) or newer** — `MenuBarExtra` with the window style.
2. **A Swift toolchain** to build — either the Xcode command‑line tools or
   Xcode. Check with `swift --version` (needs Swift 5.9+).
3. **Claw-ED installed** so there's something to launch:

   ```bash
   pip install clawed
   # verify it's on your PATH:
   which clawed     # e.g. /opt/homebrew/bin/clawed
   ```

   If `clawed` isn't on your PATH (common with some `venv`/`pyenv` setups), the
   app falls back to running the documented Python module entry point with
   `python3`. You can also point the app at a specific `clawed` or `python3`
   in **Settings** (see below).

4. **Optional: `ffmpeg`** — only needed if you use Claw-ED's narrated‑video
   tool. `brew install ffmpeg`. Not required to build or run this launcher.

---

## Build & run (no Xcode required)

From this `mac-app/` directory:

```bash
swift build            # compile
swift run              # launch the menu-bar app
```

`swift run` launches the executable directly. The app forces itself into
"accessory" (menu‑bar‑only) mode at startup, so **no Dock icon appears** even
without a bundle. Look for the graduation‑cap icon in your menu bar; click it
to open the panel.

To stop: use **Quit** in the panel (this also stops the Claw-ED server), or
press `Ctrl‑C` in the terminal you ran `swift run` from.

Release build:

```bash
swift build -c release
.build/release/ClawEDMenuBar
```

### How it launches Claw-ED

The app resolves exactly one logical command — start the Claw-ED server — in
this priority order:

1. **`clawed app --port 8000 --no-open`** (preferred) — using the `clawed`
   console script from your configured path, else from `PATH`.
2. **Python module fallback** — if `clawed` isn't found:

   ```bash
   python3 -c "import sys; sys.argv=['clawed','app','--port','8000','--no-open']; \
               from clawed._entry_router import main; main()"
   ```

   using your configured interpreter, else `python3`/`python` from `PATH`.

`--no-open` is passed because the **Mac app** opens the browser itself, and only
once the server has actually answered a health check. The arguments are
constructed by the app — never assembled from free‑form input — so the UI can't
be coaxed into running anything other than the Claw-ED server.

The child process inherits your environment with an augmented `PATH`
(`/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin`, …) so GUI‑launched
lookups for `clawed`, `python3`, and `ffmpeg` succeed. It also sets
`EDUAGENT_LOCAL_AUTH_BYPASS=1` (the same thing `clawed app` sets) so a teacher
on their own machine never hits a token wall.

### Settings (⌘,)

- **Launcher path** — leave empty to auto‑detect, or point at your `clawed`
  command or a `python3`. The window shows what was auto‑detected.
- **Port** — defaults to `8000`.
- **Open my browser when Claw-ED is ready** — on by default.

---

## Notes on the LAN URL + QR code

The QR code encodes the **LAN URL** (e.g. `http://192.168.1.42:8000`) so a phone
on the same Wi‑Fi can scan and open Claw-ED.

Important: by default `clawed app` binds to **`127.0.0.1`** (localhost only), so
the LAN URL won't actually connect until LAN sharing is enabled on the server
side. The app shows the LAN URL/QR for convenience and states this caveat in the
panel. Wiring an explicit, clearly‑labeled "Allow phones on my Wi‑Fi" opt‑in
(which would launch the server bound to `0.0.0.0` with a visible warning) is a
planned follow‑up — see `docs/product/CLAWED_DESKTOP_PLAN.md`.

---

## Project layout

```
mac-app/
├── Package.swift                 # SwiftPM executable (no third-party deps)
├── README.md                     # this file
└── Sources/ClawEDMenuBar/
    ├── ClawEDMenuBarApp.swift    # @main App + MenuBarExtra + AppDelegate
    ├── MenuBarContentView.swift  # the popover panel (status, URLs, QR)
    ├── SettingsView.swift        # ⌘, settings (launcher path, port)
    ├── ServerController.swift    # Process management + health polling
    ├── LaunchPlan.swift          # resolves the fixed `clawed app` invocation
    ├── QRCode.swift              # CoreImage CIQRCodeGenerator helper
    └── AppEnvironment.swift      # constants, settings, LAN IP discovery
```

This target is **Swift only**. It is not part of the Python CI
(ruff / mypy / pytest) and does not touch any Python, templates, or config.

---

## Ship a signed & notarized `.app` (next steps)

`swift run` is fine for development, but to hand a teacher a real, double‑click
app, wrap the binary in an `.app` bundle, then **codesign** and **notarize** it
so Gatekeeper opens it without warnings.

### 1. Make it a true menu‑bar app bundle

Create an `App.app/Contents/` structure:

```
ClawED Menu Bar.app/
└── Contents/
    ├── Info.plist
    ├── MacOS/ClawEDMenuBar        # the `swift build -c release` binary
    └── Resources/                  # AppIcon.icns, etc.
```

The **`Info.plist`** must include:

- `CFBundleIdentifier` — e.g. `app.macxlabs.clawed.menubar`
- `CFBundleName` / `CFBundleDisplayName` — `Claw-ED`
- `CFBundleExecutable` — `ClawEDMenuBar`
- `CFBundlePackageType` — `APPL`
- `CFBundleShortVersionString` / `CFBundleVersion`
- **`LSUIElement` = `true`** — this is the key that makes it a menu‑bar‑only
  "agent" app (no Dock icon, no main window) at the bundle level. (The code
  also sets `.accessory` activation as a fallback.)
- `LSMinimumSystemVersion` = `14.0`
- `NSHumanReadableCopyright`

> Tip: For a smoother build, you can instead create a tiny **Xcode** "App"
> target, drop these same Swift files in, set the deployment target to macOS 14,
> add `LSUIElement = YES`, and let Xcode produce/sign the bundle. SwiftPM is
> kept here so it builds without Xcode; the Xcode route is the easiest path to a
> distributable bundle.

### 2. Prerequisites for signing

- An **Apple Developer Program** membership.
- A **Developer ID Application** certificate in your login keychain
  (`security find-identity -p codesigning -v` to list).
- A notarization credential profile saved once:

  ```bash
  xcrun notarytool store-credentials "CLAWED_NOTARY" \
    --apple-id "you@example.com" \
    --team-id  "YOURTEAMID" \
    --password "app-specific-password"
  ```

### 3. Codesign (hardened runtime)

```bash
codesign --deep --force --options runtime --timestamp \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  "ClawED Menu Bar.app"

# verify
codesign --verify --deep --strict --verbose=2 "ClawED Menu Bar.app"
```

This app uses no special entitlements (no sandbox, no camera/mic). It does spawn
a child process and make local network requests; standard Developer ID signing
with the hardened runtime is sufficient. If you later **sandbox** the app, you'll
need `com.apple.security.network.client` and to rethink launching an external
interpreter (sandbox restricts spawning arbitrary executables) — see the plan
doc.

### 4. Notarize & staple

```bash
# zip the bundle for submission
ditto -c -k --keepParent "ClawED Menu Bar.app" "ClawED-Menu-Bar.zip"

# submit and wait
xcrun notarytool submit "ClawED-Menu-Bar.zip" \
  --keychain-profile "CLAWED_NOTARY" --wait

# staple the ticket so it works offline
xcrun stapler staple "ClawED Menu Bar.app"
xcrun stapler validate "ClawED Menu Bar.app"
```

### 5. Distribute

- Zip the stapled `.app` (or wrap in a signed `.dmg`) and host it (GitHub
  Releases, MacxLabs site, etc.).
- Verify a clean download opens with **no Gatekeeper prompt**:
  `spctl --assess --type execute --verbose "ClawED Menu Bar.app"` should report
  `accepted`.

See `docs/product/CLAWED_DESKTOP_PLAN.md` for the full roadmap, including
optional **login‑item auto‑start**.
