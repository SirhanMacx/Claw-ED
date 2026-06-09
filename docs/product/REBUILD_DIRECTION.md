# Claw-ED — Rebuild Direction & Handoff (the clear plan)

> **Read this first. This supersedes the WebView-over-tunnel approach.** Written
> 2026-06-08 by the prior session for a **fresh instance** to execute. It is the
> agreed direction from Jon (the CEO/teacher), not a menu of options.

---

## 0. The decision, in one paragraph

Claw-ED becomes **two native apps that share one design and one agent**:

- **Claw-ED for Mac** — a real **desktop app** (like **Claude Desktop / Codex
  desktop**) that *houses the agent*. The agent runs **inside the app, locally**,
  with full Mac/file/tool/skill access. Chat-first. This is the primary product.
- **Claw-ED for iPhone** — the **remote counterpart**. Same design, mobile
  layout. It tethers to the Mac app's agent over the network (the tunnel + auth
  we already built) so the teacher can drive their Mac agent on the go.

**Not** a browser. **Not** a web page in a WebView pointed at `localhost`. A real
app you launch from the dock, with the agent living in it. The iOS app is its
remote, exactly the way the ChatGPT app drives Codex.

The clawed Python agent backend (Gateway + `agent_core` + ~45 tools + approval
gate) is **kept and reused**. What we **rebuild** is the *experience* (a chat-first
agent UI), the *shell* (native Mac app instead of a menu-bar launcher + browser),
and we **add general Mac-control tools** so it's genuinely Codex-like, not just
education flows.

---

## 1. Why we pivoted (honest postmortem)

The prior build drifted into: a FastAPI **education web app** (onboarding wizard,
lesson-form UI) exposed over a Cloudflare tunnel, with the iOS app a thin
**WebView** pointed at it. Three things were wrong:

1. **It's a web app in a WebView, not an agent app.** Jon's vision was always a
   Codex/Claude-Code-style agent on the Mac with a phone remote. What got built
   *looks and feels* like a structured web form, and the agentic power is buried.
2. **The tether is fragile.** WebView → Cloudflare tunnel → self-hosted web
   server is a brittle way to do "phone controls my Mac agent." It kept failing
   the basics (in-app connect spinner, camera, menu-bar status).
3. **I validated the wrong layer.** I proved things with `curl` and the iOS
   Simulator — which *passed* — while the things Jon actually touches (the
   menu-bar status, the on-device tether, the camera) didn't work. **Curl green
   ≠ working.** The new rule (below) fixes this.

**The non-negotiable working rule for the rebuild:** *Something is "done" only
when it works where the user uses it.* The **Mac app we CAN verify locally** (the
agent runs on the same Mac). The **iOS app we cannot see** — so we build the Mac
app until it's genuinely good locally, **then** wire the tether, and **Jon tests
each iOS step**. No declaring victory from a proxy.

---

## 2. Product shape

```
┌─────────────────────────────┐         pair / tether          ┌──────────────────┐
│        Claw-ED for Mac       │◀───────  (QR + token)  ───────▶│ Claw-ED for iPhone│
│  (native desktop app)        │   over the existing https      │  (remote control) │
│                              │   tunnel — ONLY for remote     │                  │
│  ┌────────────────────────┐  │                                │  same chat,      │
│  │  Agent UI (chat-first) │  │                                │  mobile layout,  │
│  └────────────────────────┘  │                                │  camera capture  │
│  ┌────────────────────────┐  │                                └──────────────────┘
│  │  clawed agent (local)  │  │   ← Python sidecar, localhost only for the Mac app.
│  │  Gateway + agent_core  │  │     The Mac app supervises it (no tunnel needed
│  │  + tools + approvals   │  │     for the Mac's own use → solid, fast, offline-ok).
│  └────────────────────────┘  │
└─────────────────────────────┘
```

Key principle: **the Mac app talks to its own embedded agent over loopback** — no
tunnel, no flakiness, works offline. The **tunnel is only the iOS remote's path**
to reach the Mac. This cleanly separates "the app + agent" (must be rock-solid)
from "the remote" (best-effort, nice-to-have on the go).

---

## 3. Architecture recommendation

### 3.1 Tech stack — RECOMMENDED: Tauri 2 (Mac) + Capacitor (iOS) + one shared web UI

Build the UI **once** as a web frontend (the design system + agent chat), and
render it in two native shells:

| Layer | Choice | Why |
|---|---|---|
| **Mac app shell** | **Tauri 2** (Rust + system WebView) | Real native app (dock icon, own window, menus) — *not a browser*, exactly like Claude Desktop. Tiny notarizable binary (fits the **direct-download from macxlabs.app** distribution decision). Spawns + supervises the Python agent as a **sidecar**. |
| **iOS app shell** | **Capacitor** (keep/evolve the existing `ios-app/`) | Already built; renders the same web UI; tethers to the Mac. |
| **Shared UI** | One web codebase (recommend **Svelte** or **React + Vite**, or even framework-free) | Build-once → **guaranteed matching Mac + iOS design** (Jon's explicit ask). Iterate fast. Use the **frontend-design skill** on it. |
| **Agent** | **clawed** Python (Gateway + agent_core), unchanged core | Runs locally as a sidecar inside the Mac app; reused as-is. |

**Why this over the alternatives:**
- **vs. fully-native SwiftUI (Mac+iOS):** SwiftUI is the most "native" and shares
  Swift across platforms, and we already have a SwiftPM Mac app + Swift iOS
  knowledge. **But** you'd build the rich agent-chat UI *twice* (no build-once),
  lose the web design-sharing + the frontend-design skill's web output, and still
  must embed Python. Choose SwiftUI **only if** Jon wants maximal native feel and
  accepts the double UI build. *(Document this as the live alternative — it's a
  legitimate call.)*
- **vs. Electron:** Electron is what Claude Desktop uses and is well-trodden, but
  binaries are large and notarization heavier. **Tauri** gives the same
  "web-in-a-real-app" with a fraction of the footprint — better for direct
  download. (If the team already knows Electron and wants zero risk, it's a fine
  fallback.)

> **Note on "I don't want it in a browser":** Tauri/Electron is **not a browser** —
> it's a native app that happens to render its UI with web tech (Claude Desktop is
> literally this). The thing Jon rejected was "open `localhost:8000` in Safari,"
> not web-rendered UI inside a real app. Make sure the app *feels* native: real
> window chrome, menus, dock icon, no URL bar, no Safari.

### 3.2 The Python agent as a local sidecar
- Bundle clawed with **PyInstaller** → a single binary the Mac app spawns on
  launch and supervises (health-check, restart). The existing Swift
  `ServerController.swift` / `LaunchPlan.swift` in `mac-app/` is a working model
  of "supervise the agent process" — port that logic into the Tauri (Rust) side
  or keep a thin Swift helper.
- The Mac app hits the sidecar on `127.0.0.1:<port>` (loopback). **No keychain,
  no tunnel** for the Mac's own use. (Keep `PYTHON_KEYRING_BACKEND=null` — see
  Lessons.)
- The **tunnel (cloudflared) + device-token auth** we already built stays — it's
  *only* started when the teacher wants the iPhone remote to reach this Mac.

### 3.3 Tether (iOS ⇄ Mac) — keep what works, fix what didn't
- Reuse: the **named Cloudflare tunnel** (`clawed.macxlabs.app`), **device-token
  bootstrap → cookie** auth (works in curl; see §7), the **pairing QR**.
- The previous spinner was the WebView connect handoff. In the new model the iOS
  app is *still* a web UI in Capacitor, so keep the **15s connect watchdog**
  (already shipped in build 4) and, when you wire the remote, **verify the cookie
  survives on a real device** (ITP) — if it doesn't, switch the bootstrap cookie
  to `SameSite=None; Secure` (server-side, one line in `clawed/api/server.py`),
  or move the token to an `Authorization: Bearer` header injected by Capacitor.

---

## 4. Agent capabilities — what makes it Codex-like

The backbone exists. `clawed/gateway.py` `Gateway.handle(message, teacher_id,
transport)` is the conversational entry; `agent_core/` has the tool-calling loop
(`core.py`/`loop.py`, `max_agent_iterations`), an **approval gate**
(`approvals.py`), memory, a planner, and ~45 tools.

**What's missing for a true "control my Mac" agent (ADD these, all behind the
approval gate):**
1. **Shell / command execution tool** — run a command on the Mac (`run_command`),
   streamed output, **approval-gated** (this is the heart of Codex/Claude-Code).
   There is currently **no** general shell tool (only `generate_animation` and
   `self_equip` shell out for their own narrow purposes).
2. **General file read/write** — today `file_manager.py` is **sandboxed to a
   workspace output dir**. Add broad, approval-gated file access (read/write/edit
   anywhere the teacher allows).
3. **Keep all ~45 education tools** (generate_lesson, generate_assessment,
   curriculum_map, drive_*, research, …) — these are Claw-ED's *differentiator*
   vs. generic Codex. The pitch: *"Codex for teachers"* — a real Mac agent that
   also knows pedagogy + your curriculum.

**Security:** an agent that runs shell commands and is reachable over a tunnel is
real RCE-on-your-Mac. The **approval gate is the safety** (agent must request
approval before destructive/system actions; default-deny; show exactly what it
will run). This is acceptable for a single-user, token-gated, personal tool — it's
what Codex/Claude-Code do — but treat the approval UX as a first-class feature,
not an afterthought.

---

## 5. Frontend design — workshopped directions

Use the **frontend-design skill** to build these out. Brand anchor: the existing
**clay `#C96442`** + **cream `#FAF9F5`** (the app icon). Audience: teachers —
warm, calm, trustworthy, **not childish, not sterile**. Think *"a serene
co-teacher's desk,"* closer to Linear/Notion calm with academic warmth.

A polished, self-contained mockup of the recommended direction (Mac **and** iOS
side-by-side, so the match is visible) ships with this handoff:
**`docs/product/design/clawed-agent-mockup.html`** — open it in a browser to see
the target. It is a *design reference*, not production code.

### Direction A — "Calm Studio" ✅ RECOMMENDED (the mockup embodies this)
Cream canvas, clay accent, soft rounded cards (10–12px), generous whitespace, a
warm **serif for the agent's voice/headings** + humanist sans (Inter/SF) for UI.
Chat-first: a centered conversation, a quiet left rail (Sessions · Skills ·
Workspace), a top bar with the model + a **real agent status pill** (fixes the
old menu-bar lie), a rich composer (text · attach · **camera** · voice · ⌘K
command palette). Tool calls render as calm **action cards** ("Running `ls
~/Desktop`", "Generating Unit 3 lesson…") that expand for detail. Approvals are
clear inline cards: *"Claw-ED wants to run `…`  [Details] [Allow once] [Always]
[Deny]."*

### Direction B — "Focused Console" (ship as a DARK THEME of A, not a separate app)
Warm-dark mode, monospace for command/tool output, for when the teacher wants the
"agent doing things on my Mac" to feel transparent + technical. Same layout as A.
A theme toggle, not a fork.

### Direction C — "Notebook" (adopt the IDEA, not a separate design)
Generated artifacts (lessons, docs, slides, assessments) are **first-class inline
objects** in the conversation — openable, editable, exportable — so the chat reads
like a lesson journal. This leans into Claw-ED's education strength. Fold this
*pattern* into A (artifact cards), don't build a third UI.

**Synthesis:** A is the design system; B is its dark theme; C is how
education-artifacts render inline. One coherent product.

### Shared design tokens (starting point — refine in the skill)
```
--clay:      #C96442;  --clay-ink: #A24E32;   /* primary accent / pressed */
--cream:     #FAF9F5;  --paper:    #F4F1EA;    /* canvas / raised surfaces */
--ink:       #2A2722;  --ink-soft: #6B645B;    /* text / secondary text   */
--line:      #E7E1D6;  --ok:#2F8F6B; --warn:#C9893F; --stop:#B4493A;
--radius: 12px;  --shadow: 0 1px 2px rgba(40,32,22,.06), 0 8px 24px rgba(40,32,22,.06);
font-ui: 'Inter', -apple-system, system-ui;   font-voice: 'Newsreader','Iowan',Georgia,serif;
```

### Component inventory (build once, share Mac/iOS)
message bubble (user/agent) · **action/tool card** · **approval card** ·
streaming dots · **composer** (text+attach+**camera**+voice+send) · session list
item · **skill card** · **artifact card** (lesson/doc/slide) · status pill ·
command palette (⌘K) · pairing/QR panel (Mac) · pair-scan (iOS).

### Key screens
- **Mac:** Agent Chat (primary) · Skills gallery · Workspace/files · Settings
  (provider/model, **Pair iPhone** QR, permissions/approvals).
- **iOS:** Agent Chat (full-screen, camera composer) · Sessions drawer · Pair
  screen · Approvals as bottom sheets.

---

## 6. Phased plan (each milestone PROVEN before the next)

> Build the Mac app to genuinely-good locally before touching iOS. Verify on the
> real surface, not curl.

- **M0 — Spike the shell (½ day).** Bare Tauri app that opens a window showing a
  "hello" web page and **spawns + health-checks the clawed sidecar** on loopback.
  Proof: app launches, agent process is up, window renders. *(Or the SwiftUI
  equivalent if that path is chosen.)*
- **M1 — Agent chat that acts on the Mac (the core).** Wire the web chat UI to
  `/gateway/chat`; add the **shell + general-file tools** behind the approval
  gate. Proof (local, by the agent author): type *"make ~/Desktop/clawed-test and
  write hello.txt"* → approval card → it does it → confirms. This is the Codex
  moment. Build the "Calm Studio" design here.
- **M2 — Make it genuinely good.** Streaming, tool/approval UX, artifact cards
  (inline lessons/docs), Skills gallery, command palette, dark "Console" theme,
  the education tools surfaced well.
- **M3 — Package the Mac app.** PyInstaller the agent → Tauri sidecar bundle →
  Developer-ID sign + **notarize** → DMG/download on macxlabs.app. *(Signing
  pipeline + cert already exist — see §7.)*
- **M4 — iOS remote.** Point the Capacitor app's shared UI at the paired Mac's
  tunnel URL; reuse pairing QR + token-cookie; keep the connect watchdog. **Jon
  tests every step on his iPhone** (we are blind to it). Camera capture for docs.
- **M5 — Polish + ship** both (TestFlight build for iOS, notarized DMG for Mac).

---

## 7. What to REUSE (already built + working — don't redo)

- **Agent backend:** `clawed/` — Gateway, `agent_core` (loop, planner, memory,
  approvals), ~45 tools, provider config. The **OpenRouter test-connection bug is
  fixed** (commit `a6d3b25`); agent reaches `minimax/minimax-m3`.
- **iOS signing pipeline (fully autonomous, documented):** cert `65R855S7DZ`
  ("Apple Distribution: JON ANTHONY MACCARELLO"), profile `ClawED App Store api`,
  the **ASC API cert-mint recipe** + `/tmp/asc/` tooling + `build_ipa.sh` +
  `ExportOptions-manual.plist`. See **`docs/product/HANDOFF.md`** §"iOS signing —
  SOLVED". Archive **unsigned** then **export-sign** (avoids the Capacitor
  framework-profile error).
- **TestFlight delivery:** internal group `Internal`
  (`964a6f26-102f-4fed-957f-92fb2c0714ae`, all-builds) + tester
  `sirhanmacx@icloud.com`. New builds auto-appear. (A build can be VALID yet
  invisible with no group — that was a real gotcha.)
- **Tunnel + auth:** named cloudflared tunnel `clawed.macxlabs.app`, device-token
  → cookie bootstrap (303 + `Set-Cookie`, verified end-to-end in curl), pairing QR
  logic (`mac-app/.../QRCode.swift`, `connect.js`).
- **Mac agent-supervision logic:** `mac-app/Sources/ClawEDMenuBar/{ServerController,
  LaunchPlan,AppEnvironment}.swift` — a working "spawn + supervise the agent"
  reference to port into the new shell.
- **Brand + the better bits of the current CSS** (`clawed/api/static/claude-theme.css`).

## 7b. What to REBUILD / RECONSIDER
- **The frontend/UX** — replace the education templates (`index/dashboard/generate/
  lesson.html`) with the **chat-first agent UI**. Keep the education *tools*, lose
  the form-first *experience*.
- **The Mac shell** — evolve from "menu-bar launcher + browser" to a **real app
  window** (Tauri). The menu-bar app's "server not connected" was a stale/buggy
  status check (the agent was verifiably up on :8000) — don't port that check;
  build a correct status pill driven by the local sidecar health.
- **Add** the general **shell + file tools** (§4).

---

## 8. Hard-won lessons + constraints (carry forward)

- **Verify on the real surface, not a proxy.** Curl/sim green ≠ works for Jon. Mac
  app = verify locally; iOS = Jon tests each step (we can't see his devices;
  computer-use/screen access has been down all session).
- **Keychain is radioactive on this Mac.** The login keychain is locked/out-of-sync;
  **any `security`/`codesign` call hangs on a GUI password prompt** (even
  read-only `security show-keychain-info`). The agent must run with
  `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`. Signing uses a **separate
  `/tmp` keychain we control** (never the login keychain). Never enter Jon's
  password; never reset the keychain.
- **Never print** the `.p8`, API keys, or the device token value.
- **Don't weaken verifiers** (ruff/mypy/tests; `swift build`; real-WebKit sim for
  iOS). The 65 mypy "BaseModel subclass" errors in `clawed/models.py` are
  pre-existing pydantic noise, not yours.
- **Branch `claude/app-experience`; no merge to main; no vX tag.** Commits this
  session through `cf0a739`.
- **Distribution decided:** Mac = **notarized direct download** from macxlabs.app
  (full power, not the sandboxed Mac App Store). iOS = App Store/TestFlight.
- **It's free** — built to grow MacxLabs. ~$0 spend beyond the $99 Apple account.

---

## 9. Open decisions for the fresh instance (ask Jon)

1. **Shell: Tauri (recommended) vs. fully-native SwiftUI** — biggest fork. If Jon
   wants maximal native feel + accepts a double UI build, SwiftUI; else Tauri +
   shared web UI for build-once design match.
2. **Design direction** — confirm "Calm Studio" (the mockup) is the vibe; tune
   palette/voice. Dark "Console" theme now or later?
3. **Scope of Mac-control** — how far does the shell tool go on day one (read-only
   commands first? full exec behind approval immediately?).
4. **Education tools surfacing** — which 5–6 tools are front-and-center vs. in the
   Skills gallery.
5. **Name/identity** — keep "Claw-ED"? The app is `com.macxlabs.clawed`.

## 10. First action for the fresh instance
Read this doc + `docs/product/HANDOFF.md` (signing/keychain/TestFlight reality) +
open `docs/product/design/clawed-agent-mockup.html`. Then confirm decisions §9
with Jon, and start **M0 → M1** (Tauri shell + clawed sidecar + agent chat that
acts on the Mac, verified locally). Don't touch iOS until the Mac app is good.
