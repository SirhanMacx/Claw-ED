# Claw-ED → plug-and-play edtech miracle

**Vision (Jon):** any educator with a Mac and a hard drive runs their own AI
co-teacher — zero friction. Empower every teacher, not just the technical ones.

This doc tracks the path there: what's verified working, the one open product
decision, and the remaining backlog. The build loop works this list; items that
need Jon's product judgment are flagged.

## ✅ Verified working (this build cycle)
- **Flagship lesson generation** — was broken (reasoning-budget starvation);
  now generates *complete* lessons (instruction + vocabulary + sourced primary
  documents + assessment). Proven end-to-end.
- **Multi-agent pipeline reliability** — the researcher→writer→reviewer path was
  crashing on minimax-m3 (and would on most smaller/free models) from two causes,
  both now fixed: (1) the writer's `max_tokens` was capped at 6000, so a reasoning
  model's output truncated and trailing sections were dropped → lifted to 32000
  (no artificial caps); (2) cross-model field drift (`content` instead of
  `teacher_script`, a lone object where a list was expected, an omitted section)
  crashed the whole lesson → a `MasterContent` before-validator now normalizes
  drift and degrades a missing section to a safe empty. A model that returns most
  of a lesson now yields most of a lesson. (commit 7db63c8, 10 regression tests)
- **Proven on a real ingested unit** — ingested a teacher's actual Global History
  unit, then generated lessons on minimax-m3 that are *grounded in the ingested
  sources* and *match the teacher's voice*: authentic, attributed primary sources
  (Copernicus/Galileo/Bacon/Newton; King James I/Bossuet/Locke), the teacher's
  CRQ + Enduring-Issue structure, and even a near-verbatim reproduction of the
  teacher's signature Do-Now hook captured during ingestion. Both the single-agent
  (phases) and multi-agent paths produce complete, classroom-ready lessons.
- **Loads the learned persona, not a stale default** — lesson generation resolves
  the rich ingested `~/clawed_output/persona.json` via `load_persona_or_exit`,
  with a graceful starter-persona fallback for teachers who haven't ingested yet.
- **Config survives a broken keychain** — a locked / headless / SSH macOS keychain
  (`KeyringError -25291`) used to crash config load with "not configured" *even
  when a valid key was in secrets.json*. Keychain failures now fall through to the
  environment / secrets file. (commit 093a07a, 6 regression tests)
- **Complete enrichment** — fixed the `MasterContent → DailyLesson` converter
  that silently dropped vocabulary + primary sources on every lesson.
- **Any model / any provider** — provider-aware + rate-limit-aware phase retries:
  single-model providers retry their model, Ollama rotates its chain, free /
  rate-limited tiers back off and recover instead of failing the lesson.
- **No crashes on bad data** — every stored-record parse (persona/unit/lesson/
  materials) now degrades to a clean 4xx, never an opaque 500.
- **Live "show the work" progress UI** on the Create screen.
- **Runs on a free model** (`nvidia/nemotron-3-super-120b-a12b:free`) — proof
  that a teacher needs no paid key to get real output.

## ⚠️ Open product decision (Jon) — the #1 plug-and-play gap
The first-run **web wizard** (`/`, `index.html`) flows Welcome → Upload‑files‑or‑
describe‑style → Persona → **Generate** — but it **never sets up an AI provider**.
Provider/key setup lives only in **Settings** (a small link in Step 1). So a fresh
teacher can reach "Generate Your First Lesson" with no provider connected and hit
a wall. For true plug-and-play, the wizard must guarantee a working provider
*before* the generate step.

**Decision needed — how should first-run handle the AI provider?**
1. **Inline setup step** — add a "Connect your AI" step to the wizard
   (recommended one tap: free OpenRouter or local Ollama), so setup happens
   in-flow. Most seamless; most build effort.
2. **Routed + guarded** — keep setup in Settings, but the wizard detects "no
   provider" and routes the teacher there with a friendly CTA before Generate.
   Lighter; one extra click.
3. **Zero-config default** — ship a working default (e.g. a bundled/free model
   or a guided 1-tap free key) so it *just works* with no setup at all. The
   strongest "miracle" but depends on a reliably-free path.

**Status (verified this cycle):** The web app serves the whole no-terminal path
end-to-end — `/`, `/generate` (Create), `/settings`, static assets, and the
health endpoint all return 200, and `/api/health` reports the right
provider/model with `llm_connected: true`. The detection mechanism that all
three options need — **`GET /api/onboarding/detect`** — is built, tested, and
verified serving (it correctly surfaced the configured OpenRouter key as
"ready to use"). **But nothing in the wizard UI calls it yet** — it's a ready
backend waiting on the front-end wiring, which lives in the stashed onboarding-
wizard work and is gated on this decision. In other words: the hard part
(reliable detection) is done; the remaining work is choosing the flow and
connecting it.

A capable model is also required for the deep lesson pipeline (structured JSON +
long output) — the default/recommended provider must clear that bar.

## Backlog (build loop, no product decision needed)
- [x] (e) Lesson-output quality pass (humanities) — judged two real, ingested-
      source lessons; both read like a master teacher's and match the teacher's
      style. ✅
- [ ] (e2) **Generalization** — verify quality holds for a *non-humanities*
      subject/grade (science or math). Both lessons proven so far are document-
      based Global History. Ingest a different-subject corpus and judge whether
      the pipeline adapts (or over-imposes CRQ/primary-source structure where it
      doesn't fit). The "any subject, any grade" promise hinges on this.
- [~] (e3) **Voice-match score** — root cause found + fixed: the CLI showed a
      constant "3.0/5.0" because it called `score_voice_match` WITHOUT an LLM
      client (the neutral fallback). Now wired to the real model (commit
      e9de26b). Remaining: confirm the now-real score is well-calibrated — needs
      one paid lesson run to observe an actual score, so deferred with the other
      paid checks.
- [ ] (d) Confirm a full lesson generates COMPLETE on the **free** model E2E
      (free model historically truncates long structured output; the drift
      normalizer should now make partial output usable rather than fatal).
- [x] (f) Deep README claim-by-claim audit — **honest, no vaporware.** Every
      documented command + subcommand exists; high-risk features all have real
      backing modules; specific numbers check out ("70+ tells" → 125 actual,
      "12 pedagogical checks" → ~12-14 real with auto-retry); `clawed demo`
      (no-API-key path) runs and produces a compelling sample. ✅
- [x] One-click Mac menu-bar launch (`mac-app/`) — **reviewed, core solid.**
      Find-clawed→start→health-poll→auto-open-browser is correctly wired
      (`LaunchPlan` resolves clawed/PATH/python + augments the minimal GUI PATH;
      `ServerController` start/stop/health/teardown all correct; relies on the
      keyring-resilience fix to survive GUI-launched keychain access). ✅
      Open gap (NOT a bug — disclosed in UI): the **phone QR / LAN URL won't
      connect by default** because `clawed app` binds `127.0.0.1` and the
      launcher has no LAN-exposure opt-in. Adding a "share on Wi-Fi" toggle
      that launches with `--host 0.0.0.0` is the fix — but it's security-
      sensitive (LAN exposure) and Swift (can't verify headless), so it needs
      Jon's intent before building.

## Guardrails
Parked: no merge to `main`, no release tag — no rush to market. Testing on the
free model to conserve paid credits for demo/alpha.
