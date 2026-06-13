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

## What already exists (verified 2026-06-11)
- ✅ **iOS thin client** (`ios-app/`, Capacitor): a polished CONNECT screen
  (`www/connect.js` + `index.html`) — scan the Mac's `clawed://` QR, type a
  server URL, or auto-open the remembered server; the phone becomes the full
  agent web app.
- ✅ **Mac menu-bar app** (`mac-app/`, SwiftPM): finds + launches the engine,
  health-polls, opens the browser, shows the remote tunnel and LAN URLs, and
  renders pairing QR codes.
- ✅ **LAN bind toggle** (shipped today, 9ad1787): "Share on my Wi-Fi" →
  `clawed app --host 0.0.0.0` so a phone on the same Wi-Fi can reach the Mac.
- ✅ **Remote bridge**: the named Cloudflare tunnel at
  `https://clawed.macxlabs.app` is live behind device-token auth; launchd keeps
  the agent and tunnel running.
- ✅ **The agent itself**: FastAPI web app + ~40 `agent_core` tools (files, web
  search, web read, config edit, Drive, scheduling) behind a risk-classified
  approval gate. Runs on the Mac.
- ✅ iOS build 5 is valid and in internal TestFlight
  (`internalBuildState=IN_BETA_TESTING`) for `com.macxlabs.clawed`; build 5,
  screenshots, metadata, and privacy URL are ready for public submission once
  the portal-only category/App Privacy fields are set.

## Gaps
- ⚠️ **QR-scanner plugin not installed** — connect screen falls back to manual
  URL entry for the in-app Scan QR button. One-scan pairing already works via
  the normal iPhone Camera opening the `clawed://` link; a direct in-app scanner
  remains optional.
- ⚠️ **Public App Store submission** — blocked in the web portal only: set
  primary category **Education**, secondary category **Productivity**, and App
  Privacy **Data Not Collected**, then resubmit version 1.0. Current version
  state is `DEVELOPER_REJECTED`, not waiting for Apple review.
- ❌ **Notarized downloadable Mac `.app`** with the Python engine bundled (so a
  teacher needs no `pip`). The Tauri 2 app and bundled agent exist; Developer ID
  signing/notarization is blocked on the Account Holder certificate.

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
- [x] A4. **Superseded by build 5.** ASC shows build **5** for
      `com.macxlabs.clawed` as `VALID`, not expired, and selected on App Store
      version 1.0; beta state is `IN_BETA_TESTING` for internal TestFlight. ✅
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
4. Open **TestFlight** → install/open **Claw-ED** (current build 5). Scan the Mac
   pairing QR with the iPhone Camera, or type the LAN URL (e.g.
   `http://192.168.1.42:8000`) and tap **Connect**.
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
- ✅ **(a) Mac pairing QR — DONE (cbb1596):** the menu shows an "Open on your
  phone (anywhere)" QR encoding `clawed://connect?url=https://clawed.macxlabs.app
  &token=<device-token>`. The token is read from `~/.eduagent/api_token` locally
  and only leaves by being scanned off-screen. `swift build` clean.
- ✅ **(b) launchd always-on — DONE (b699f9c):** `scripts/launchd/install.sh`
  installs `com.macxlabs.clawed-agent` + `com.macxlabs.clawed-tunnel` (RunAtLoad
  + KeepAlive). Installed + verified live: agent 200, tunnel 4 edges,
  protected-without-token 401, cookie-auth 200 — all through the launchd-managed
  services. The Mac serves `clawed.macxlabs.app` from boot now.
- ✅ **(c) iOS build 3 → TestFlight — SHIPPED (2026-06-08).** Jon said "go ahead,"
  so the codesign/keychain block was solved **autonomously via an App Store Connect
  API cert-mint** — no login-keychain prompt at any point:
  1. Minted a fresh **Apple Distribution** cert through the ASC API (account had
     0 distribution certs, so no limit issues).
  2. Built the signing identity in a **dedicated keychain** (`/tmp/clawed-signing.keychain-db`,
     password I set → codesign authorized non-interactively; the **locked login
     keychain was never touched**) with the WWDR G3 intermediate for a full chain.
  3. Created + installed an **App Store provisioning profile** (`ClawED App Store api`)
     binding the new cert to `com.macxlabs.clawed`.
  4. Archived **unsigned** (`CODE_SIGNING_ALLOWED=NO`) then **export-signed**
     (`-exportArchive` manual) — so the CocoaPods framework targets don't choke on
     a profile (frameworks sign with the identity only; the app gets the profile).
  5. `altool --upload-app` → **UPLOAD SUCCEEDED** (Delivery UUID `92116b15…`),
     IPA signed `Apple Distribution: JON ANTHONY MACCARELLO (Y8MX8Q77B2)` → WWDR
     → Apple Root. Tooling: `/tmp/asc/` (`asc_api.py`, `make_cert.py`,
     `make_profile.py`, `setup_keychain.sh`, `build_ipa.sh`, `ExportOptions-manual.plist`).
- ✅ **(d) Current build state:** build 5 is valid in App Store Connect and is the
  current build to install/test; build 3 remains the historical signing fix.

### Production status (verified 2026-06-11) — SHIPPED end-to-end for testing
Backend production-ready (secure always-on tunnel + agent via launchd, device-token
auth, phone-login validated over the real https tunnel) **AND iOS build 5 is valid
and in internal TestFlight**. Jon installs the current TestFlight build, scans
the Mac QR, and opens straight into his classroom agent from anywhere. The
prototype is real, end-to-end — phone → tunnel → Mac agent. Public App Store
submission still needs the portal-only category and App Privacy fields, then a
fresh resubmission of version 1.0.

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
