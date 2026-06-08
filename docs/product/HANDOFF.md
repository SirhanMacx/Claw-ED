# Claw-ED — Handoff for future instances

**Read this first, then [`PROTOTYPE.md`](./PROTOTYPE.md) (the product north-star).**
This doc is the *operational* map: where things live, how to run + verify, the
one remaining blocker, and the hard rules that keep you from breaking Jon's
machine. PROTOTYPE.md has the milestone narrative; don't duplicate it here.

_Last updated: 2026-06-08 · branch `claude/app-experience` · tip `f132f66`._

---

## TL;DR — current state

- **Backend is production-complete and LIVE.** Always-on agent + Cloudflare named
  tunnel run as launchd services; device-token auth; full phone-login validated
  end-to-end over the real `https://clawed.macxlabs.app` tunnel in the iOS
  Simulator's WKWebView. CI green on `claude/app-experience`.
- **The ONLY thing left is signing the iOS build for TestFlight — and it is
  Jon-gated** (a macOS keychain authorization only he can grant). See
  [§ The one blocker](#the-one-blocker--ios-signing-jon-gated).
- **Do NOT run `codesign` / `xcodebuild archive` / any `security` command to
  "check" or "try" anything.** That is what spammed Jon with keychain password
  prompts. See [§ The keychain rule](#-the-keychain--codesign-rule-most-important).

---

## What Claw-ED is

A teacher's self-hosted AI co-teacher:

- **Mac app** (`mac-app/`, SwiftPM menu-bar) — launches + supervises the agent,
  health-polls, shows a pairing QR. Ships (eventually) as a **notarized direct
  download** from macxlabs.app — full power (file access, subprocesses), *not*
  the sandboxed Mac App Store.
- **The agent** (`clawed/`, FastAPI on `127.0.0.1:8000`) — ~40 `agent_core`
  tools (files, web search/read, config, Drive, scheduling) behind a
  risk-classified approval gate. Runs on the always-on Mac (Jon's Mac mini),
  with the teacher's files.
- **iPhone companion** (`ios-app/`, Capacitor thin client) — a WebView that
  points at the Mac's agent over the network. Never touches the Mac's files; it
  *is* the agent UI, served from the Mac. Ships on the App Store (`com.macxlabs.clawed`).

Phone → tunnel → Mac agent. The phone is a remote control; the Mac does the work.

---

## The one blocker — iOS signing (Jon-gated)

iOS **build 3** code is ready + committed (`CURRENT_PROJECT_VERSION=3`). It is
**not shipped** because `codesign` cannot use the signing private key in this
headless context: `find-identity` lists the cert, but *using* the key needs a
keychain authorization with no GUI to approve it (`codesign --sign` → hang/exit
124). You cannot enter Jon's keychain password, and must not.

**Unblock = Jon does ONE of these (he must say so explicitly):**
1. Runs `security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k <pw> ~/Library/Keychains/login.keychain-db` (prompts for his login password), **then** you archive → export → `altool` upload → verify VALID autonomously; **or**
2. Says **"mint a new cert"** (you create a fresh signing identity); **or**
3. Archives + uploads build 3 himself in Xcode (Product → Archive → Distribute → TestFlight).

**Until Jon explicitly authorizes one of those: do not touch signing at all.**
The standing health-loop (below) waits; it never runs codesign speculatively.

When authorized, the exact ship sequence lives in the `/loop` prompt that drives
this work (archive → `xcrun altool --upload-app … --apiKey … --apiIssuer …` →
update PROTOTYPE.md → commit + push → CI green → notify Jon → **STOP**). Never
print the `.p8` contents or enter an Apple password.

---

## ⚠️ The keychain / codesign rule (MOST IMPORTANT)

**Never run `security`, `codesign`, or `xcodebuild archive` to test, check, or
explore.** On Jon's machine the **login keychain is locked / out of sync with
his account password**, so *any* `/usr/bin/security` call **blocks on a GUI
password dialog** — including the supposedly read-only `security
show-keychain-info` (verified: it hung until killed, 2026-06-08). Every
speculative call pops "**security wants to use the login keychain**" on Jon's
screen. Repeated `codesign` attempts spammed him badly enough that fixing the
prompts became its own multi-session task.

Rules:
- The agent's launchd wrapper sets `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`
  so the **agent never touches the keychain**. Keep it that way.
- `clawed/config.py` wraps keychain reads in a 2s timeout + disable-cache
  (`_call_with_timeout`, `_keyring_disabled`) so a hung Keychain falls through to
  `~/.eduagent/secrets.json`. **Never weaken this.**
- For diagnostics, stay **file-based** (read scripts, plists, configs). Do not
  shell out to `security`.
- The only real fix for the locked keychain is **Jon's** (unlock / re-sync the
  login keychain password, or restart). You cannot do it autonomously and must
  never reset/delete the keychain (destructive).

### Machine-state note (keychain-prompt incident, 2026-06-08)
Jon reported recurring "security wants to use the login keychain" prompts. Root
causes found + neutralized (all reversible, plists preserved):
- **`com.codex.crypto-bounty-radar`** — an **hourly** LaunchAgent that shelled
  out to `security find-generic-password`; the high-frequency spammer. **Stopped
  + disabled**; also added an opt-in guard (`CRYPTO_RADAR_USE_KEYCHAIN=1`) in its
  script so it can't resume prompting.
- **`com.reviewarcade.claude-watch`** — a dead `KeepAlive` crash-looper (its
  `/tmp` script was gone) burning CPU + 17 MB of errors. **Stopped + disabled.**
  (Not a keychain source, just cleanup.)
- **Residual (unavoidable, Jon-gated):** the **agent CLIs themselves**
  (Claude Code / Codex) read their OAuth token via `security find-generic-password`
  on each session start — see `claude-code-source-build/.../macOsKeychainStorage.ts`.
  Against the locked keychain, that prompts "less often, but still." Only Jon
  unlocking/re-syncing the keychain stops it.

---

## Repo map (key files)

| Area | Path | Notes |
|---|---|---|
| Agent API | `clawed/api/server.py` | FastAPI app; `_check_page_auth` uses `local_bypass_ok` |
| Auth | `clawed/api/deps.py` | `local_bypass_ok` (Cf-Ray ⇒ no loopback bypass), `require_auth` (cookie/Bearer) |
| Keychain-safe key load | `clawed/config.py` | timeout + disable-cache; **never weaken** |
| Health | `clawed/api/routes/settings.py` | `GET /api/health` — the prompt-free probe |
| iOS connect | `ios-app/www/connect.js` | auto-connect, token→cookie via form-POST to `/api/auth/bootstrap` |
| Mac menu-bar | `mac-app/Sources/ClawEDMenuBar/MenuBarContentView.swift` | pairing QR (`clawed://connect?url=…&token=…`) |
| Always-on services | `scripts/launchd/install.sh` (+ `uninstall.sh`, `README.md`) | the two launchd services |
| Tunnel config | `~/.cloudflared/config.yml` | `clawed` tunnel → `localhost:8000`, ingress `clawed.macxlabs.app` |
| Auth tests | `tests/test_auth_tunnel.py` | Cf-Ray bypass, cookie auth over tunnel, bootstrap attrs |
| Product north-star | `docs/product/PROTOTYPE.md` | milestones A/B/C, what's done, Jon's test steps |

Local secrets (never print values): device token `~/.eduagent/api_token`,
provider key `~/.eduagent/secrets.json`.

---

## How it runs (deployment) + health check

Two user LaunchAgents (RunAtLoad + KeepAlive) make the Mac serve
`https://clawed.macxlabs.app` from boot:
- `com.macxlabs.clawed-agent` — agent on `127.0.0.1:8000` (loopback only)
- `com.macxlabs.clawed-tunnel` — `cloudflared` named tunnel (the sole public ingress)

```bash
bash scripts/launchd/install.sh        # install / update + load
launchctl list | grep clawed           # status (pid + last exit)
curl -s -m 6 http://127.0.0.1:8000/api/health   # prompt-free health probe
launchctl kickstart -k gui/$(id -u)/com.macxlabs.clawed-agent   # restart agent (no keychain ops)
```

The tunnel requires the device token — loopback is bypassed, tunnel traffic
(carries a `Cf-Ray` header) is not. That's the security boundary; keep it closed.

### Standing health loop
A `/loop` keeps the agent alive: each wake does **only** the `curl /api/health`
above and `kickstart` if down — **no keychain/codesign commands**. It ships the
iOS build **only** when Jon explicitly authorizes signing, then **STOP**s.

---

## Verify before commit (never weaken a verifier)

- Python: `ruff`; `mypy --strict` (ignore the known import-untyped/no-any-return
  noise only); `pytest` with `EDUAGENT_EMBEDDER=tfidf -o addopts=""` via
  `/opt/homebrew/bin/python3`.
- Swift: `cd mac-app && swift build`.
- iOS: `cap sync` + an Xcode/Simulator build (real WebKit, not headless Chromium).
- `HEARTBEAT.md` / repo verifiers as configured.

---

## Guardrails (hard constraints)

- **No merge to `main`. No `vX` tag.** Work on `claude/app-experience`.
- **Never** enter Apple ID / 2FA / keychain credentials; **never** print the
  `.p8`, API keys, or the `api_token` value.
- **Never** run `security` / `codesign` speculatively (see the keychain rule).
- **Never** weaken a verifier or the auth boundary. Security-sensitive paths
  (remote/LAN/auth): default-closed, loud warnings, approval gate intact.
- Keychain is **off-limits for autonomous repair** — reset/delete is destructive;
  hand the unlock/re-sync to Jon.
- Keep the launchd services alive. cloudflared / xcodebuild / codesign need
  `dangerouslyDisableSandbox` *when Jon has authorized that work*.
