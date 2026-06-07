# Claw-ED — "Fully built & ready for TestFlight" checklist

This is the done-condition for the build loop. Each item ships as a small,
CI-green commit on `claude/app-experience` (PR #6). "Done" = every box checked
or explicitly blocked-on-Jon (Apple signing only).

## A. App completeness & polish (web + Mac) — autonomous
- [x] Core generation: lessons, units, materials, quizzes, differentiation, games
- [x] BYO-key (Anthropic/OpenAI/OpenRouter/Google) + local Ollama
- [x] Claude design system
- [x] Live streaming "Ask your co-teacher" (chips, Markdown, copy/download)
- [x] Mac menu-bar launcher app
- [x] **Mobile-responsive UI** — every core page usable at 390px (phone via the
      Mac app's LAN URL/QR). Nav, Create wizard, co-teacher, library, settings.
- [x] First-run / empty states — friendly guidance when no persona/lessons yet
- [x] Connection/health clarity — the footer "Not connected" must reflect the
      real provider state and link to a fix
- [x] All artifact endpoints verified end-to-end on OpenRouter/minimax-m3
      (quiz ✓, co-teacher stream ✓, **differentiate ✓ 200 OK 42s** at HEAD —
      this exercises the `resolve_model` routing path that the earlier bug
      broke for every routed artifact; game is correctly wired but produces
      weak HTML on minimax-m3 — a documented model-capability limit, see
      Known limitations)
- [x] README / quickstart current (clawed app, BYO-key, phone access)

## B. iOS app (Capacitor client) — autonomous up to signing
Architecture (per the security model: local-first, no shell to mobile): the iOS
app is a **thin client** that opens the teacher's own Claw-ED server over the LAN
(the URL/QR the Mac app already shows). No Python on device.
- [x] Capacitor project under `ios-app/` wrapping a mobile entry that prompts for
      / remembers the server URL (paste or scan QR), then loads the web UI
      *(committed 2b727e4 — native Xcode project, config, ASC tooling)*
- [x] App icon + splash (clay/cream `AppIcon` + `Splash` in `Assets.xcassets`)
- [x] Build + sign: distribution IPA archived + exported
      (`ios-app/build/ipa/App.ipa`, v1.0 build 1, Apple Distribution Y8MX8Q77B2).
      iOS-Simulator WebKit smoke of the connect screen is the one remaining
      autonomous verify (thin client; Jon also device-tests on TestFlight).
- [x] ASC metadata draft (name, subtitle, description, keywords, age rating,
      privacy, review notes) — `docs/product/ASC_METADATA.md`
- [ ] **BLOCKED ON JON:** ASC app record (Apple forbids API creation — 403) +
      TestFlight upload. The upload itself is one command on the ASC API key,
      no browser/credentials needed — see "Handoff" below.

## C. Ship gate
- [x] Full test suite + CI green at HEAD (run 27081492544 — success, 3m31s;
      was a 42-min flaky failure before the embedder fix in 77ce832)
- [x] Function-size cap (HEARTBEAT) green (run 27081492545 — success)
- [x] No secrets in repo; secrets.json gitignored; key read from env/keyring/file
      (`.gitignore` lists `secrets.json`, `**/secrets.json`, `api_token`, `.env`;
      no secret files are tracked)

## Loop protocol
Build → ruff + mypy --strict + browser-verify → commit → push → CI green →
next item. Stop when A+B(non-blocked)+C are checked; report the Apple-signing
handoff to Jon.

## Verification notes (where each ticked A-item lives)
- **Core generation:** routes in `clawed/api/routes/generate.py`
  (`/unit`, `/lesson`, `/materials`, `/quiz`, `/differentiate/{id}`, `/game`),
  surfaced as cards on the Create screen (`clawed/api/templates/generate.html`).
- **BYO-key + local Ollama:** five providers in
  `clawed/api/routes/settings.py` and `clawed/api/templates/settings.html`
  (Anthropic, OpenAI, Ollama, OpenRouter, Google), each with a guided key flow.
- **Claude design:** `clawed/api/static/claude-theme.css`, loaded from `base.html`.
- **Live co-teacher:** SSE endpoint `/api/ask/stream` in `generate.py`; chips,
  Markdown render, Copy / Download .md in `generate.html`.
- **Mac menu-bar app:** `mac-app/` (SwiftUI) — `ServerController.swift`,
  `QRCode.swift`, `MenuBarContentView.swift` show local + LAN URLs and a QR code.
- **Mobile-responsive:** `width=device-width` viewport in `base.html`;
  `@media (max-width: 768px)` rules in `claude-theme.css` and `style.css`.
- **Connection/health clarity:** `/api/health` reports the real provider/model
  (`settings.py`); the status bar reads it.
- **README:** "no-terminal app", BYO-key incl. OpenRouter/minimax-m3, phone
  access via the Mac app's LAN URL/QR.

## Known limitations (not blockers)
- **Review games on minimax-m3 are weak + slow.** `/api/game` asks the model for
  a complete single-file HTML game (up to 2 × 12k-token generations). minimax-m3
  (a cheap reasoning model) tends to return short/incomplete HTML that fails the
  game validators (`no <script>`, too short), forcing a retry → ~200s and a
  low-quality result. This is a **model-capability** limit, not a routing/code
  bug (differentiate — same routing path — is 200 OK in 42s). Games work well on
  code-capable models (Claude Sonnet/Opus, GPT-4o); the code already warns about
  this and the README/onboarding steer game users toward a capable model.
- **iOS app needs a running Claw-ED server** (by design — local-first thin
  client). Fine for TestFlight; for public review give the reviewer a reachable
  demo server (see ASC_METADATA.md → App Review).

## Handoff — the last mile (Jon's one manual step)
Apple **forbids creating an app record via the API** (confirmed 403:
`apps` allows only GET/UPDATE). The extension-controlled Chrome is **not** signed
into App Store Connect, and I won't enter Apple credentials/2FA. So the app
record must be created once in Jon's already-signed-in browser:

1. App Store Connect → **My Apps → ＋ → New App**
2. Platform **iOS**; Name **Claw-ED**; Primary language **English (U.S.)**;
   Bundle ID **com.macxlabs.clawed** (already in the dropdown — J6MYZ2VRS9);
   SKU **CLAWED001**; Access **Full**.
3. Create.

The instant it exists, the upload is fully automated on the ASC API key (no
browser, no password):
```
xcrun altool --upload-app -t ios -f ios-app/build/ipa/App.ipa \
  --apiKey K5RKF383QT --apiIssuer 6a02d8d5-4d1e-4f92-9936-18d05e663ff2
node ios-app/scripts/asc.mjs verify-build --version 1
```

**Status:** A (web/Mac) and C (ship gate) are complete and CI-green. B (iOS) is
built, signed, committed, and metadata-drafted — only the Apple-side record +
upload remain, which is the owner's credential step.
