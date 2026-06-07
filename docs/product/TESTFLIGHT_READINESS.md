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
- [ ] No secrets in repo; secrets.json gitignored; key read from env/keyring/file

## Loop protocol
Build → ruff + mypy --strict + browser-verify → commit → push → CI green →
next item. Stop when A+B(non-blocked)+C are checked; report the Apple-signing
handoff to Jon.
