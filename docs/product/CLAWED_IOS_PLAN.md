# Claw-ED iOS — Thin-Client Plan

> Positioning: the iOS app is a **phone/tablet front door** to a teacher's own
> Claw-ED server. The engine stays in Python on the Mac; the app is a calm,
> local-first WebView that points at the URL the Mac already shows. It is the
> mobile sibling of the menu-bar Mac app (`mac-app/`) and follows the same
> guardrails as `docs/product/CLAWED_DESKTOP_PLAN.md`.

This is intentionally the smallest thing that's useful: scan the Mac QR with
the iPhone Camera, open the `clawed://` pairing link, remember the server, and
render the teacher's running Claw-ED. Manual URL entry remains available. No
Python runs on device.

---

## Architecture

```
┌─────────────────────┐         same Wi-Fi          ┌──────────────────────────┐
│  iPhone / iPad      │   http://192.168.x.x:8000   │  Teacher's Mac           │
│  Claw-ED (Capacitor)│  ─────────────────────────► │  clawed app (uvicorn)    │
│                     │                             │  clawed.api.server:app   │
│  www/ CONNECT screen│  ◄─────────────────────────  │  127.0.0.1 / 0.0.0.0 :8000│
│  → WebView navigates│        HTML / API / JSON    │  GET /api/health         │
│    to that URL      │                             │  SQLite + LLM stay here  │
└─────────────────────┘                             └──────────────────────────┘
```

- **Native shell:** [Capacitor](https://capacitorjs.com) (`@capacitor/ios`),
  `appId` `com.macxlabs.clawed`, `appName` "Claw-ED", `webDir` `www`.
- **Bundled web content:** exactly one screen — the **CONNECT** screen
  (`ios-app/www/`). It is dependency-free vanilla HTML/CSS/JS. It does **not**
  bundle the Claw-ED web app.
- **Hand-off:** once the teacher provides a valid base URL, the WebView either
  posts a paired device token to `/api/auth/bootstrap` or does a direct
  `location.replace(url)` to the local server. From that point the app shows the
  teacher's real Claw-ED. The CONNECT screen is only seen on first launch, after
  "Use a different server," or when the saved server cannot be reached.
- **Server contract:** matches the rest of the repo — default
  `http://<host>:8000`, health probe `GET /api/health` (no auth, no DB/LLM —
  `clawed/api/routes/settings.py`). If the port/host/health route change in
  `clawed/`, update this app's default (`DEFAULT_PORT` in
  `ios-app/www/connect.js`) and the Mac app's `AppEnvironment.swift` together.
- **Discovery:** the Mac menu-bar app renders QR codes for phone pairing. The
  preferred pairing path is the normal iPhone Camera opening a `clawed://` deep
  link handled by the app. The in-app **Scan QR** button remains an optional
  direct-scanner fallback.

### Why a thin client (not a port of the engine)

The engine is Python (FastAPI + SQLite + the curriculum pipeline) and is not
something to reimplement or cross-compile onto iOS. Apple's sandbox also forbids
spawning interpreters, so "run the server on the phone" is a non-goal for the
same reason the Mac App Store path is hard for the desktop app
(`CLAWED_DESKTOP_PLAN.md`, Stage 1/3). The teacher already runs the server on a
Mac; the phone just needs to reach it.

---

## Data & security model

Consistent with `docs/PRIVACY_MODEL.md` ("no third-party analytics") and the
desktop guardrails:

- **Local-first, LAN-only.** The app talks to one origin: the teacher's own
  server on the local network. There is no Claw-ED cloud, no account system, and
  no MacxLabs backend. The shell sends nothing to MacxLabs.
- **No telemetry / no analytics SDKs.** None bundled, none planned.
- **Stored values** are the last-good server URL (`clawed.serverUrl`) and, when
  pairing with a remote/tunnel server, the device token (`clawed.serverToken`).
  The token is posted once to `/api/auth/bootstrap`; the server sets its own
  first-party cookie. "Use a different server" clears both values.
- **Cleartext on the LAN is expected and scoped.** Teacher servers are plain
  `http://` on the local network (no public TLS). `capacitor.config.json` enables
  `cleartext` so the WebView can load those LAN origins. This is a deliberate
  local-network allowance, not an open door to the public internet:
  - The CONNECT screen only accepts `http`/`https` URLs and defaults a bare host
    to the documented `:8000`.
  - For App Store review, the iOS `Info.plist` should scope App Transport
    Security to local networking rather than a blanket `NSAllowsArbitraryLoads`
    — i.e. `NSAllowsLocalNetworking = true` (plus `NSAllowsArbitraryLoads` only
    if a teacher's server uses a non-`.local` hostname that ATS still blocks).
    This is documented here as the reviewer-facing justification: "the app is a
    controller for the user's own server on their LAN."
  - iOS will prompt for **Local Network** permission on first connect; that is
    expected and correct for a LAN client.
- **No arbitrary command surface.** Unlike a terminal, the app can only navigate
  to a URL the user supplied. There is no command field and no code execution.

### Threat-model notes (honest limitations)

- A malicious actor on the same Wi-Fi who knows the URL could reach the server —
  but that is a property of the *server's* LAN exposure (the Mac side gates this
  behind an explicit, off-by-default opt-in), not of this client. The client
  surfaces the "same Wi-Fi only" framing so the teacher understands the trust
  boundary.
- Because LAN traffic is `http`, it is unencrypted on the local network. This is
  acceptable for a classroom LAN and is the same posture as the Mac app's LAN
  URL. If end-to-end encryption is ever required, that is a server-side change
  (TLS on the Mac), and the client would simply use the `https://` URL.

---

## Toolchain status (recorded 2026-06)

Captured on the build host while scaffolding:

| Tool          | Version            | Notes                                            |
| ------------- | ------------------ | ------------------------------------------------ |
| `node`        | v25.9.0            | ≥18 required by Capacitor.                       |
| `npm`         | 11.12.1            | OK.                                              |
| `npx`         | 11.12.1            | OK.                                              |
| `xcodebuild`  | Xcode 26.3 (17C529)| iOS toolchain present.                           |
| CocoaPods     | not verified here  | Capacitor needs it for `cap sync`; `sudo gem install cocoapods` if missing. |

What is built and what is deferred:

- ✅ **Built now:** `package.json`, `capacitor.config.json`, native
  `ios/App/App.xcworkspace`, the CONNECT screen (`www/index.html` +
  `connect.js` + `styles.css`), `clawed://` deep-link handling via
  `@capacitor/app`, token bootstrap, a 1024×1024 placeholder icon, and docs.
- ✅ **Verified locally:** `npm run doctor`, `npm run sync:ios`, and native iOS
  build/archive steps have run on the build host during the release pass.
- ⏳ **Follow-ups:** optional direct in-app barcode scanner
  (`@capacitor/barcode-scanner`); the full icon set via `@capacitor/assets`;
  the final brand icon (Ed mascot / MacxLabs) to replace the placeholder.

---

## Apple signing & TestFlight

The native app is ready to archive when signing credentials are present on the
build host. No private certificates, provisioning profiles, or App Store Connect
API keys should be committed to the repo.

Release checklist:

1. **Sync web assets:** from `ios-app/`, run `npm run sync:ios`.
2. **Open in Xcode** (`npm run open:ios`) → **App** target → **Signing &
   Capabilities**:
   - Confirm **Team** is `Y8MX8Q77B2`.
   - Confirm/register the bundle identifier `com.macxlabs.clawed`.
   - Automatic signing is fine for a first build.
3. **Archive & upload:** Product → Archive → distribute to **App Store Connect**
   for TestFlight, or run the equivalent `xcodebuild -archivePath ... archive`
   plus export/upload flow.
4. **App Store review framing:** the privacy answers are "no data collected"; the
   ATS/local-network and camera (if added) usage strings explain the LAN-client
   nature of the app.

---

## Guardrails (apply to every stage)

- **No telemetry.** No analytics SDKs, ever (`docs/PRIVACY_MODEL.md`).
- **Local-first only.** The app connects to the user's own server; there is no
  cloud backend and no account.
- **No arbitrary command surface.** The app can only navigate to a user-supplied
  URL — no terminal, no code execution.
- **Don't touch the Python surface.** This app lives entirely under `ios-app/`;
  it is not in the Python CI and must not modify Python, templates, or config.
- **Match the existing health/port contract.** Keep `DEFAULT_PORT` in
  `ios-app/www/connect.js` in sync with `clawed/` and `mac-app/`.
- **Calm, trustworthy UI.** Claude palette (cream `#FAF9F5`, clay `#C96442`,
  serif), plain language, honest caveats about same-Wi-Fi access.
```
