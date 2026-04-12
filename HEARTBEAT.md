# HEARTBEAT.md — Runtime health and self-monitoring

> This document describes the operational health contract for Claw-ED. It
> is the companion to `SOUL.md` (via Claw-STU): if SOUL.md describes *who
> the teaching voice is*, this describes *how we know Claw-ED is still
> working as intended*.

## Why this exists

The April 2026 technical audit surfaced a recurring failure pattern:
**silent degradation**. Exceptions swallowed, prompts subtly drifting,
tests passing while the actual teacher experience decayed. This file
codifies the invariants that must hold for Claw-ED to be considered
healthy. A failed heartbeat is never silent.

## Invariants

### Global invariants

These must hold everywhere in the codebase. Violations are bugs.

1. **No swallowed exceptions.** Every `except` either handles the specific
   exception class explicitly or re-raises. Bare `except:` and bare
   `except Exception: pass` are forbidden in production code.
2. **No circular imports.** All imports resolve at module load time.
3. **Function size cap.** No function exceeds ~100 lines (relaxed from
   STU's 50 due to ED's 69K LOC). Functions over 100 lines are tracked
   for decomposition.
4. **Quality gate invariants.** All 12 pedagogical checks must run.
   Auto-retry on failure. No lesson ships below threshold.
5. **Voice invariants.** AI-ism removal runs on all output. `soul.md` is
   the source of truth for teacher voice.
6. **Image pipeline invariants.** Vision model filter runs on all fetched
   images. No broken image paths in exported output.
7. **Security invariants.** Bearer token auth on all teacher routes.
   Timing-safe comparison everywhere. No secrets in logs.
8. **Test invariants.** All tests pass before every push. No dead/skipped
   test bodies.

## Observability

- **Structured logging** from day one. Every generation event is logged
  with `teacher_id`, `module`, `event_type`, and `payload`.
- **No secrets in logs.** API keys, bearer tokens, and teacher credentials
  never appear in log output.
- **Metric counters** (post-MVP): generation latency, quality gate pass
  rate, export success rate, image pipeline rejection rate.

## Health endpoint

`GET /health` returns:

```json
{
  "status": "ok",
  "version": "4.11.2026",
  "invariants": {
    "quality_gate_active": true,
    "voice_filter_active": true,
    "image_filter_active": true,
    "provider_reachable": true
  }
}
```

Any `false` value flips `status` to `"degraded"` and logs at WARN.

## Failure modes we explicitly plan for

1. **LLM provider outage.** Generation gracefully fails with a
   teacher-visible message; no partial or corrupted output is saved.
2. **Quality gate failure.** Auto-retry up to the configured limit. If
   all retries fail, the teacher is notified — no silent downgrade.
3. **Prompt drift.** Snapshot tests catch unexpected changes to system
   prompts before they ship.
4. **Image pipeline failure.** Broken images are filtered out; the lesson
   is delivered with a placeholder rather than a broken link.
5. **Export format corruption.** Export tests validate round-trip
   integrity for every supported format.

## How to change this file

Deliberate, reviewed, human-approved. A new invariant means a new test.
