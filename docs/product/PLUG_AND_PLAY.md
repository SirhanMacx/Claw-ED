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
- [ ] (e3) **Voice-match calibration** — the multi-agent reviewer self-scored
      "voice match 3.0/5.0" on a lesson that actually reproduced the teacher's
      signature hook. The reviewer rubric (or the writer's persona injection)
      is mis-calibrated; tighten `multi_agent_reviewer.txt` / persona context.
- [ ] (d) Confirm a full lesson generates COMPLETE on the **free** model E2E
      (free model historically truncates long structured output; the drift
      normalizer should now make partial output usable rather than fatal).
- [ ] (f) Deep README claim-by-claim audit (shallow pass: all claims have
      backing code; verify each actually works — no vaporware).
- [ ] One-click Mac menu-bar launch is smooth end-to-end (`mac-app/`).

## Guardrails
Parked: no merge to `main`, no release tag — no rush to market. Testing on the
free model to conserve paid credits for demo/alpha.
