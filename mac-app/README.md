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
- Shows the **local URL**, the remote tunnel URL, and the opt-in **LAN URL**,
  with pairing QR codes for the phone companion.
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
- **Share on my Wi-Fi** — off by default. When enabled, the launcher starts
  `clawed app` with `--host 0.0.0.0` so phones on the same trusted Wi-Fi can
  open the LAN QR code. Restart Claw-ED after changing this setting.

---

## Notes on phone pairing

The menu has two phone paths:

- **Anywhere:** `https://clawed.macxlabs.app`, encoded as a `clawed://` pairing
  link with the local device token. The token is read from `~/.eduagent/api_token`
  and only leaves by being scanned from the teacher's screen.
- **Same Wi-Fi:** the LAN URL (e.g. `http://192.168.1.42:8000`), also encoded as
  a `clawed://` pairing link when LAN sharing is enabled.

Important: by default `clawed app` binds to **`127.0.0.1`** (localhost only), so
the LAN URL won't connect from a phone until **Share on my Wi-Fi** is enabled in
Settings and the server is restarted. That opt-in launches the server bound to
`0.0.0.0` and the UI shows a visible warning because anyone on that Wi-Fi can
try to open it.

---

## Project layout

```
mac-app/
├── Package.swift                 # SwiftPM executable (no third-party deps)
├── README.md                     # this file
└── Sources/ClawEDMenuBar/
    ├── ClawEDMenuBarApp.swift    # @main App + MenuBarExtra + AppDelegate
    ├── MenuBarContentView.swift  # the popover panel (status, URLs, QR)
    ├── SettingsView.swift        # ⌘, settings (launcher path, port, LAN sharing)
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
- A **Developer ID Application** certificate from the Account Holder.
- A notarization credential profile saved once.

On Jon's machine, read `docs/product/HANDOFF.md` before any signing work. Do not
run exploratory `security`, `codesign`, or archive commands against the login
keychain; the locked keychain has produced repeated GUI prompts. The current
direct-download Mac packaging path lives under `desktop/` and is driven by
`desktop/scripts/sign_and_notarize.sh` after the Account Holder provides the
Developer ID certificate.

### 3. Codesign (hardened runtime)

This app uses no special entitlements (no sandbox, no camera/mic). It does spawn
a child process and make local network requests; standard Developer ID signing
with the hardened runtime is sufficient. If you later **sandbox** the app, you'll
need `com.apple.security.network.client` and to rethink launching an external
interpreter (sandbox restricts spawning arbitrary executables) — see the plan
doc.

Use the scripted signing/notarization flow from the current desktop packaging
lane once the Developer ID certificate is available. Avoid ad hoc local command
experiments on the locked-keychain machine.

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
