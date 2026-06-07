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
- [ ] All artifact endpoints verified end-to-end on OpenRouter/minimax-m3
- [x] README / quickstart current (clawed app, BYO-key, phone access)

## B. iOS app (Capacitor client) — autonomous up to signing
Architecture (per the security model: local-first, no shell to mobile): the iOS
app is a **thin client** that opens the teacher's own Claw-ED server over the LAN
(the URL/QR the Mac app already shows). No Python on device.
- [ ] Capacitor project under `ios-app/` wrapping a mobile entry that prompts for
      / remembers the server URL (paste or scan QR), then loads the web UI
- [ ] App icon + splash (reuse the asset-gen skill)
- [ ] Build + smoke-verify on the iOS Simulator (real WebKit, per ios-apps skill)
- [ ] ASC metadata draft (name, subtitle, description, age rating, privacy)
- [ ] **BLOCKED ON JON:** Apple Developer signing + TestFlight upload (credentials)

## C. Ship gate
- [ ] Full test suite + CI green at HEAD
- [ ] Function-size cap (HEARTBEAT) green
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

The iOS Capacitor client (section B) is **in progress**; Apple Developer signing
remains the owner's step.
