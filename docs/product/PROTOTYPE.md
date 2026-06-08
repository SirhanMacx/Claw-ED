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
- [ ] A2. (DEFERRED to a follow-up build) QR-scanner plugin for one-scan
      pairing. Manual URL entry already works, so it doesn't block the first test.
- [x] A3. **Done (23ed99e)** — the Mac menu now shows the LAN URL + QR (which
      encodes `NetworkInfo.lanURL`) **only when Share-on-Wi-Fi is on**; with
      sharing off it nudges the teacher to enable it instead of showing a QR
      that can't connect. `swift build` clean. ✅
- [x] A4. **Already done — no rebuild needed.** ASC shows TestFlight build **1
      (VALID, not expired)** for `com.macxlabs.clawed`, uploaded 2026-06-07 after
      the connect shell was committed; the iOS app has had **zero changes since**,
      and the local archive that produced it contains `connect.js`. So the
      current connect-shell app is already installable from TestFlight. ✅
- [x] A5. Test steps written (below). ✅
- **Jon tests A:** Mac mini + iPhone on the same Wi-Fi.

### ✅ Simulator end-to-end test (done by Claude, 2026-06-07)
Built the iOS app for the iPhone-17 Simulator, installed + launched it, and drove
the connect flow against the live Mac agent (`http://127.0.0.1:8000`). **Result:
the native app loaded and rendered the full agent web app inside the WKWebView**
(onboarding wizard, lesson cards, sample content) — cleartext http + cross-origin
API all working. Screenshots: `/tmp/sim_connect.png` (connect screen),
`/tmp/sim_agent.png` (agent loaded in-app). The core mechanism — *phone app runs
the Mac agent over the network* — is verified end-to-end, not just reasoned.
- **P1 RESOLVED (e8393f5):** the off-origin-nav browser bar is gone — set
  `server.allowNavigation:["*"]` so the agent loads seamless full-screen in the
  app's own WKWebView (verified: no Safari, only com.macxlabs.clawed running).
- **P2 DONE (a2ddee1):** one-tap pairing — the Mac QR now encodes
  `clawed://connect?url=<server>`; scanning with the phone Camera opens the app
  (@capacitor/app + `clawed` URL scheme + connect.js appUrlOpen handler) and
  auto-connects. Verified in sim: iOS recognizes the scheme + prompts "Open in
  Claw-ED" (the teacher's one tap). Manual entry stays as fallback.
- **P-AUTO DONE (2c9e1fe) — the "open it and it's just there" win.** The phone
  app now **auto-connects on launch**: once paired, it opens straight into the
  Mac agent with no connect screen and no typing — Jon's "everything should
  happen inside the app… like Codex/ChatGPT… should be easier." On launch it
  decides deep-link → remembered-server → manual-form, and health-checks
  `GET /api/health` behind a cancelable "Opening your classroom" interstitial so
  an unreachable Mac falls back to a **friendly retry** instead of the dead
  WebView error page that made build 1 feel "busted." **Verified by Claude on
  the iPhone-17 Simulator against the live Mac agent — all three states:**
  - saved + reachable → opens straight into the agent (screenshot
    `/tmp/sim_auto_loaded.png`: onboarding + live sample, no connect screen)
  - saved + unreachable → interstitial → graceful retry form
    (`/tmp/sim_auto_fallback2.png`)
  - first run → clean connect form (`/tmp/sim_firstrun.png`)
  (Needed two server-side enables, both shipped: CORS now allows the app's
  `capacitor://localhost` origin so the probe is readable; and a
  `[hidden]{display:none!important}` rule so a hidden interstitial can't out-rank
  its own `display:flex`.)
- **NEXT — P3:** the remote bridge (Milestone B) + a device token, then ONE
  TestFlight build carrying P1+P2+P-AUTO. **Holding the TestFlight ship until the
  remote path works** — a Wi-Fi-only build would repeat the "busted/WiFi"
  complaint; the build is only worth installing once it opens from anywhere.
- **Could not (Jon away):** computer-use needs his one-time access approval, and
  there's no idb; so the *literal tap-Connect* was simulated by injecting the
  same `window.location.replace` into the installed bundle (repo source
  untouched). The real connect.js path does exactly this navigation.

### ▶ Jon's test steps — Milestone A (same Wi-Fi)
**On the Mac mini (serve the agent on the LAN):**
1. `cd ~/Projects/Claw-ED/mac-app && swift run` → the Claw-ED icon appears in the
   menu bar. Click it.
2. Click **Settings** (⌘,) → turn **ON** "Share on my Wi-Fi" (it's off by
   default). Read the orange warning — anyone on your Wi-Fi can reach it while on.
3. Back in the menu, click **Start** (or Stop→Start if it was already running) so
   the server rebinds to the LAN. The menu now shows an **"Open on your phone"**
   LAN URL + a **QR code**.
   - *Simplest alt (no menu bar):* `clawed app --host 0.0.0.0 --port 8000`, then
     get the Mac's IP from System Settings → Wi-Fi (e.g. `192.168.1.42`).
**On the iPhone (same Wi-Fi):**
4. Open **TestFlight** → install/open **Claw-ED** (build 1). On the "Connect to
   your classroom server" screen, type the Mac's LAN URL (e.g.
   `http://192.168.1.42:8000`) and tap **Connect**. (One-scan QR comes in a
   follow-up build.)
5. The phone loads the full Claw-ED agent — chat, generate a lesson, etc., all
   running on the Mac mini with your files. **That's the prototype.**

> Note: this is **same Wi-Fi only** (LAN). True "on the go" (cellular) is
> Milestone B (the Tailscale remote bridge), in progress.

## Milestone B — on-the-go (remote bridge) ← the real wall, Jon-gated
The full vision: control the Mac-mini agent from anywhere, in-app, not
Wi-Fi-dependent. Auto-connect (P-AUTO) already gives the "just opens" feel; what
remains is a reachable-from-cellular address for it to open.

### Architecture finding (2026-06-07) — pick an **https named tunnel**, not Tailscale-over-http
The iOS app's ATS is `NSAllowsLocalNetworking` (Info.plist), which permits
cleartext **only** to loopback + LAN/private ranges — **not** Tailscale's
`100.64.0.0/10` CGNAT range. So `http://100.x.y.z:8000` over a tailnet would need
the broad `NSAllowsArbitraryLoads` exception (App-Store-review friction). The
clean answer is an **https domain**, which is ATS-clean *and* App-Store-safe:
- **Recommended: Cloudflare *named* tunnel → `https://clawed.macxlabs.app`.**
  Jon already runs `macxlabs.app` on Cloudflare (the marketing site), so the zone
  exists. A `cloudflared` named tunnel gives a **stable https URL** — which is
  exactly what auto-connect wants to bake in ("just opens, anywhere") — runs
  always-on as a launchd service on the always-on Mac mini, and needs no separate
  app on the phone. Quick (`trycloudflare`) tunnels were tried and are too flaky
  (single edge connection); the named tunnel is the durable path.
- **The one-time step only Jon can do:** `cloudflared tunnel login` (a browser
  OAuth into *his* Cloudflare account — account auth I must not perform for him).
  Everything after that (create tunnel, DNS route, launchd plist, bake the URL
  into the app + auto-connect) I can script and verify locally.

### B-plan
- [ ] B1. **Device-token auth (do FIRST — buildable + verifiable without Jon).**
      A public https tunnel exposes the agent, so URL-obscurity is not enough:
      replace the blanket `EDUAGENT_LOCAL_AUTH_BYPASS` on non-loopback binds with
      a **paired-device bearer token** (phone stores it, sends it; loopback stays
      bypassed for the menu-bar/browser path). Keep the approval gate as the
      backstop for sensitive actions. Locally verifiable: `curl` with/without the
      token → 200/401, plus a sim run. **This is the next loop step.**
- [ ] B2. **Named tunnel + always-on.** `cloudflared` named tunnel +
      `clawed.macxlabs.app` DNS + launchd service; the menu-bar app shows/QRs the
      remote https URL. Gated on Jon's `cloudflared tunnel login`.
- [ ] B3. **Bake + ship.** Bake the stable URL into auto-connect (carry the
      device token), then one TestFlight build with P1+P2+P-AUTO+token. Jon
      installs once → opens straight into his classroom from anywhere.

### B progress (2026-06-08) — tunnel LIVE + SECURED; phone login is the last piece
- ✅ **Named tunnel stood up** (Jon ran `cloudflared tunnel login`): `clawed`
  tunnel created, `clawed.macxlabs.app` DNS routed, `~/.cloudflared/config.yml`
  ingress → `localhost:8000`. Test run registered **4 redundant edge
  connections** (QUIC, ewr/ord). Connector currently **stopped (door closed)**
  until phone-login lands; tunnel/DNS/config/creds persist, ready to relaunch as
  a launchd service. (cloudflared API calls need `dangerouslyDisableSandbox`.)
- ✅ **Open-door gap closed (841e062):** tunnel traffic carries a `Cf-Ray`
  header genuine loopback never has, so the local-auth bypass now keys on its
  absence — `deps.local_bypass_ok()`, shared by `require_auth` + `_check_page_auth`.
  Verified live: `/` → 200 local, 401 over (simulated) tunnel w/o token, 200 with
  Bearer. 8 regression tests (`tests/test_auth_tunnel.py`).
- ✅ **Phone login over the tunnel — DONE + VALIDATED in the real WKWebView.**
  (1) `require_auth` now accepts the `clawed_token` cookie (4a250d4); (2) the
  bootstrap cookie is `SameSite=Lax; Secure; HttpOnly` (Lax → same-origin fetch
  carries it, cross-site POST/CSRF doesn't); (3) the phone delivers it via a
  **top-level form POST** to `/api/auth/bootstrap` (token in the body, never the
  URL) — `navigateToServer` (3d5b337). The QR deep link carries the token
  (`clawed://connect?url=…&token=…`). **Verified end-to-end against the live
  https tunnel in the iPhone Simulator** (`/tmp/sim_tunnel_loaded2.png`): cold
  launch → auto-connect → bootstrap cookie → the agent web app renders with its
  authenticated `/api` content. The cross-origin / ITP worry did NOT materialize
  (the form-POST sets a first-party cookie, which WKWebView stores + sends).
  Curl over the real tunnel also confirms: health 200, no-token 401, Bearer 200,
  cookie 200. One fix: auto-connect probe 3.5s→8s (the agent's `/api/health` is
  ~4.2s over Cloudflare; 97730c9).
- ⏭ **Remaining — STEP 4 ship:** (a) Mac menu shows the **tunnel** URL + a QR
  carrying `clawed.macxlabs.app` + the device token (Swift); (b) launchd
  always-on services for the tunnel + agent (agent env `HTTPS=1` so cookies are
  Secure); (c) rebuild iOS, bump `CURRENT_PROJECT_VERSION`, archive → export →
  altool upload → poll VALID; (d) notify Jon: install the build, scan the Mac QR,
  open straight into the classroom from anywhere.

### Robustness: keychain-hang on headless launch — FIXED
On a **headless / SSH / launchd-at-login** launch with no GUI session,
`keyring.get_password` in `config.py` could **hang** in a Mach call to securityd
(not error) — the broad-except keyring-resilience only catches *errors*, so a
hang slipped through and the server never bound. This matters because the
always-on Mac service the iPhone connects to may run as a login item/daemon.
**Fixed:** each keychain call now runs under a 2s timeout (`_call_with_timeout`);
on timeout it falls through to env / `secrets.json` like any other keyring
failure. Verified — the agent binds + loads its key with NO
`PYTHON_KEYRING_BACKEND` workaround in a headless launch (previously hung forever
in `mach_msg2_trap`). A healthy GUI keychain returns in <50ms, so no change there.

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
