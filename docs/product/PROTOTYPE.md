# Claw-ED Prototype — Mac agent + iPhone remote

**Goal (Jon):** a working prototype to test on his **iPhone + Mac mini**: the
agent runs on the always-on Mac mini (with all his files); he controls it from
his phone — same Wi-Fi first, then anywhere ("on the go").

**Distribution (decided):** NOT the Mac App Store. The Mac app ships as a
**notarized direct download** from macxlabs.app (full power: file access, tools,
subprocesses — no App Store sandbox). The **iPhone companion** is a thin remote
on the App Store (it never touches the Mac's files; it talks to the Mac's agent
over the network).

**Honest boundary:** this loop builds all the code, ships a TestFlight build,
and verifies everything headlessly (compiles, server reachable, connect logic).
The final "install on my iPhone + run on my Mac mini" test is Jon's — no access
to his physical devices.

---

## What already exists (audited 2026-06-07)
- ✅ **iOS thin client** (`ios-app/`, Capacitor): a polished CONNECT screen
  (`www/connect.js` + `index.html`) — type or QR-scan the Mac's URL, it points
  the WebView at that server, and the phone becomes the full agent web app.
- ✅ **Mac menu-bar app** (`mac-app/`, SwiftPM): finds + launches the engine,
  health-polls, opens the browser, shows the LAN URL **and a QR code**.
- ✅ **LAN bind toggle** (shipped today, 9ad1787): "Share on my Wi-Fi" →
  `clawed app --host 0.0.0.0` so a phone on the same Wi-Fi can reach the Mac.
- ✅ **The agent itself**: FastAPI web app + ~40 `agent_core` tools (files, web
  search, web read, config edit, Drive, scheduling) behind a risk-classified
  approval gate. Runs on the Mac.
- ✅ iOS app already on TestFlight (`com.macxlabs.clawed`) — but as the connect
  shell; needs the verify + QR + rebuild below.

## Gaps
- ⚠️ **QR-scanner plugin not installed** — connect screen falls back to manual
  URL entry. One-scan pairing needs `@capacitor/barcode-scanner` (or similar).
- ❌ **Remote bridge** — the LAN path only works on the same Wi-Fi. "On the go"
  (cellular) needs a secure tunnel/relay. Not built.
- ❌ **Notarized downloadable Mac `.app`** with the Python engine bundled (so a
  teacher needs no `pip`). For distribution; NOT needed for Jon's own test (he
  can run the menu-bar app / `clawed app` directly).

---

## Milestone A — LAN prototype (testable on home Wi-Fi) ← FIRST
The shortest path to something Jon can actually use phone↔Mac-mini.
- [x] A1. **Verified** — loaded the Mac server at a 390px phone viewport
      (headless WebKit): the agent web app renders beautifully (onboarding
      wizard, upload/scratch cards, "Connected" status), **0 console errors**,
      4 responsive `@media` queries + viewport meta. The connect→load→use
      mechanism works; a phone gets the full agent UI. ✅
- [ ] A2. Add a QR-scanner plugin so pairing is one scan of the Mac's QR (the
      Mac already renders the LAN-URL QR). Manual entry stays as fallback.
- [x] A3. **Done (23ed99e)** — the Mac menu now shows the LAN URL + QR (which
      encodes `NetworkInfo.lanURL`) **only when Share-on-Wi-Fi is on**; with
      sharing off it nudges the teacher to enable it instead of showing a QR
      that can't connect. `swift build` clean. ✅
- [ ] A4. Rebuild the iOS app (cap sync → Xcode archive → TestFlight) and verify
      the build is VALID.
- [ ] A5. Write Jon's test steps (Mac: launch menu-bar app, toggle Share on
      Wi-Fi, show QR; iPhone: open TestFlight build, scan, use the agent).
- **Jon tests A:** Mac mini + iPhone on the same Wi-Fi.

## Milestone B — on-the-go (remote bridge)
The full vision: control the Mac-mini agent from anywhere.
- [ ] B1. Embed **Tailscale (tsnet)** in the Mac app (near-zero infra, E2E,
      NAT-traversal) OR stand up a small MacxLabs relay (branded, hosted, must be
      E2E-encrypted). Start with Tailscale for alpha.
- [ ] B2. Pairing carries the remote (tailnet) address; connect screen uses it.
- [ ] B3. Tighten remote auth — the approval gate stays the backstop for
      sensitive actions; add a paired-device secret so only Jon's phone connects.
- **Jon tests B:** iPhone on cellular, Mac mini at home.

## Milestone C — distribution + polish (for launch, not for Jon's test)
- [ ] C1. Bundle the Python engine into a notarized `.app` (PyInstaller/py2app)
      + Developer ID sign + notarize + Sparkle auto-update.
- [ ] C2. Download page on macxlabs.app.
- [ ] C3. Harden the general agent toward "everything a teacher does digitally."

---

## Guardrails
No merge to `main`, no vX tag. Never enter Apple credentials or print keys.
Verify before commit (ruff/mypy/heartbeat/tests for Python; `swift build` for
Swift; `cap sync` + Xcode build for iOS). Security-sensitive (remote/LAN/auth):
default-closed, loud warnings, approval gate intact.
