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
- [ ] (d) Confirm a full lesson generates COMPLETE on the **free** model E2E.
- [ ] (e) Lesson-output quality pass — does it read like a master teacher's
      lesson? Tighten phase prompts where it doesn't.
- [ ] (f) Deep README claim-by-claim audit (shallow pass: all claims have
      backing code; verify each actually works — no vaporware).
- [ ] One-click Mac menu-bar launch is smooth end-to-end (`mac-app/`).

## Guardrails
Parked: no merge to `main`, no release tag — no rush to market. Testing on the
free model to conserve paid credits for demo/alpha.
