# v2.3.8 Implementation Plan

**Release theme:** NLAH contract alignment — replace silent failures with explicit failure taxonomy, enforce fail-closed quality gates, and fix async/credential bugs that violate the harness contracts.

**Date:** 2026-03-30
**Base:** v2.3.7 (dc851c3)
**Spec:** claw-ed-nlah-spec.md (NLAH v0.1)

---

## P0 — Must-Ship

### P0-1: Failure taxonomy — replace silent exception swallowing in generate_lesson_bundle

**Problem:** `generate_lesson_bundle.py` has three silent exception swallowing sites that violate NLAH Section 6 (Failure Taxonomy). Exceptions are caught with bare `except Exception` and either silently passed or logged at DEBUG level. The teacher sees "success" while KB search, asset search, and persona loading all silently failed.

**Locations:**
- `clawed/agent_core/tools/generate_lesson_bundle.py:96-99` — TeacherPersona construction fails silently (`except Exception: pass`)
- `clawed/agent_core/tools/generate_lesson_bundle.py:118-130` — AssetRegistry search failures logged at DEBUG only (line 130: `logger.debug`)
- `clawed/agent_core/tools/generate_lesson_bundle.py:133-165` — CurriculumKB search failures logged at DEBUG only (line 165: `logger.debug`)

**Fix:**
1. Replace bare `pass` at line 99 with `logger.warning("Could not parse persona: %s", e)` and append to `GenerationReport.warnings`.
2. Promote both `logger.debug` calls (lines 130, 165) to `logger.warning`. Add each failure to the `GenerationReport` so it surfaces in the quality notes returned to the teacher.
3. Define failure codes as constants matching NLAH Section 6 (e.g., `PERSONA_PARSE_ERROR`, `KB_SEARCH_FAILED`, `ASSET_SEARCH_FAILED`). Log them structured: `logger.warning("NLAH_FAILURE=%s: %s", code, e)`.
4. On MasterContent generation failure (line 207-208), return the NLAH failure code (`SCHEMA_ERROR` or `API_FAILURE`) in the ToolResult text, not a raw exception string.

**Effort:** ~1 hour

---

### P0-2: Quality review fails closed, not open

**Problem:** `review_lesson_package()` in `clawed/llm.py:407-445` only wraps the JSON parsing in try/except (line 436-445). If `self.generate()` (line 435) itself throws (network error, timeout, rate limit), the exception propagates uncaught. The caller may then skip the quality gate entirely. NLAH Section 3, Stage 4 says: "Gate: quality_report.json is valid JSON with passed field → FAIL(REVIEW_FAILED) if not". The Verifier role contract (Section 2) says: "NEVER returns passed: true on exception."

**Location:** `clawed/llm.py:407-445`

**Fix:**
1. Wrap the entire method body (lines 419-445) in a single try/except that catches `Exception` and returns `{"passed": False, "issues": ["Quality review failed: <error class>"]}`.
2. Log the exception at WARNING level with the NLAH code `REVIEW_FAILED`.
3. Ensure no code path can return `{"passed": True}` without the LLM actually having produced that verdict.

```python
async def review_lesson_package(self, ...) -> dict[str, Any]:
    try:
        prompt = (...)
        raw = await self.generate(prompt, temperature=0.2, max_tokens=1000)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        result = json.loads(cleaned)
        # Guard: if LLM returned something without 'passed' key, fail closed
        if "passed" not in result:
            return {"passed": False, "issues": ["LLM response missing 'passed' field"]}
        return result
    except Exception as e:
        logger.warning("REVIEW_FAILED: %s", e)
        return {"passed": False, "issues": [f"Quality review failed: {type(e).__name__}"]}
```

**Effort:** ~30 minutes

---

### P0-3: Nested asyncio.run() in background ingest thread

**Problem:** `clawed/generation.py:632` calls `asyncio.run(extract_persona(docs, persona_cfg))` inside a background thread spawned at line 649. This works today only because the thread has no running event loop, but it's fragile — if the caller's event loop leaks into the thread context (Python 3.12+ behavior changes), it crashes with `RuntimeError: cannot be called from a running event loop`. The same codebase already has the correct pattern in `clawed/export_pptx.py:112-127` (`_run_async_safe()`), but `generation.py` doesn't use it.

**Location:** `clawed/generation.py:627-632`

**Fix:**
1. Import `_run_async_safe` from `export_pptx` (or extract it to a shared utility like `clawed/async_utils.py` since both `export_pptx.py` and `export_docx.py` already duplicate it).
2. Create `clawed/async_utils.py` with the `run_async_safe()` function (extract from `export_pptx.py:112-127`).
3. Replace `asyncio.run(extract_persona(...))` at `generation.py:632` with `run_async_safe(extract_persona(...))`.
4. Update `export_pptx.py` and `export_docx.py` to import from the shared location.

**Effort:** ~45 minutes

---

### P0-4: Stored-key vs env-var demo mode detection bug

**Problem:** `is_demo_mode()` in `clawed/demo/__init__.py:34-44` calls `resolve_credentials()` which checks env vars first, then keyring/secrets file (config.py:98-121). A teacher who stored a key via onboarding (keyring) but later unsets the env var (e.g., testing demo mode, or the env var was only set transiently in a shell) will NOT get demo mode — the stored key is silently picked up. Conversely, a teacher who *only* has a stored key (never set env vars) will never be detected as demo mode, even if the stored key has been revoked or is invalid.

The v2.3.5 changelog says "`is_demo_mode()` checks keychain" was a fix, but the current behavior means demo mode is *harder* to trigger intentionally, which confuses developers and demo presentations.

**Location:**
- `clawed/demo/__init__.py:34-44`
- `clawed/config.py:98-121` (resolve_credentials)

**Fix:**
1. Add a `CLAWED_DEMO=1` environment variable override that forces demo mode regardless of stored keys. Check this *first* in `is_demo_mode()`.
2. In `resolve_credentials()`, no change needed — the priority order (env > keyring > ollama) is correct for production use.
3. Document the override in the `/demo` command help text.

```python
def is_demo_mode(config: Any = None) -> bool:
    import os
    if os.environ.get("CLAWED_DEMO", "").strip() in ("1", "true", "yes"):
        return True
    from clawed.config import resolve_credentials
    provider, key = resolve_credentials(config)
    return provider is None
```

**Effort:** ~20 minutes

---

### P0-5: Onboarding state write protection

**Problem:** `OnboardHandler._complete_onboarding()` at `clawed/handlers/onboard.py:118-147` writes user-supplied text directly to `TeacherProfile` and `AppConfig.save()` with no validation. Issues:
- `state["name"]` (line 113) is raw `.strip()` — no length limit, no character filtering.
- `state["grade"]` (line 106) falls through to raw `text.strip()` if no numeric match — could be anything.
- `state["subject"]` (line 87) is `.title()`-cased but unbounded.
- `init_workspace(persona, config)` at line 134 silently fails (`except Exception: pass`), hiding workspace creation errors.

NLAH Section 2 (Persona Reader role): "Read-only. Returns context string." The onboarding handler is a write path and must validate before persisting.

**Location:** `clawed/handlers/onboard.py:112-136`

**Fix:**
1. Truncate `name` to 100 chars, strip non-printable characters.
2. Validate `grade` is either K, PK, or 1-12 (string). Reject anything else with a re-prompt.
3. Truncate `subject` to 100 chars.
4. Promote the `init_workspace` exception from `pass` to `logger.warning`.
5. Add a `_validate_onboard_fields()` helper that returns `(valid: bool, error_msg: str)`.

**Effort:** ~45 minutes

---

## P1 — Strongly Recommended

### P1-1: NLAH failure taxonomy as structured constants

**Problem:** The NLAH spec defines 10 failure codes (Section 6) but the codebase uses ad-hoc error strings. No structured failure reporting exists.

**Fix:**
1. Create `clawed/failure_codes.py` with an enum:
   ```python
   class FailureCode(str, Enum):
       NO_PERSONA = "NO_PERSONA"
       SCHEMA_ERROR = "SCHEMA_ERROR"
       TOPIC_DRIFT = "TOPIC_DRIFT"
       DEMO_FIXTURE = "DEMO_FIXTURE"
       EXPORT_INCOMPLETE = "EXPORT_INCOMPLETE"
       EXPORT_ERROR = "EXPORT_ERROR"
       REVIEW_FAILED = "REVIEW_FAILED"
       CONTEXT_EXCEEDED = "CONTEXT_EXCEEDED"
       API_FAILURE = "API_FAILURE"
       VOICE_MISMATCH = "VOICE_MISMATCH"
   ```
2. Wire into `GenerationReport` as an optional `failure_code` field.
3. Use these codes in `generate_lesson_bundle.py` ToolResult text (machine-parseable prefix).

**Effort:** ~1 hour

---

### P1-2: MasterContent validation gate alignment with NLAH Section 3

**Problem:** `generate_lesson_bundle.py:210-231` calls `validate_master_content()`, `validate_alignment()`, and `check_self_contained()`, but does not enforce NLAH Stage 2 gates:
- No check: "`MasterContent.guided_notes` has >= 6 fill-in-the-blank items"
- No check: "`MasterContent.primary_sources` has >= 2 sources with non-empty `text`"
- No check: "`MasterContent.exit_ticket.questions` has >= 3 questions"
- No check: "topic appears in title or aim" (TOPIC_DRIFT gate)
- No retry loop on CRITICAL issues (NLAH says: "if fails → RETRY Stage 1 with issues injected into prompt")

**Fix:**
1. Add NLAH-specified checks to `validate_master_content()` in `clawed/validation.py`.
2. In `generate_lesson_bundle.py`, classify validation errors as CRITICAL or HIGH.
3. On CRITICAL: retry `generate_master_content()` once with the issue list injected into the prompt.
4. On 3+ HIGH: log warnings, continue (matches NLAH: "no more than 3 HIGH issues").

**Effort:** ~2 hours

---

### P1-3: Quality review integration into bundle pipeline

**Problem:** `generate_lesson_bundle.py` never calls `review_lesson_package()`. The quality review LLM call (NLAH Stage 4) is entirely missing from the bundle generation flow. The `GenerationReport` accumulates warnings from validation, but the LLM-based quality review (checking timing, standards codes, vocabulary, checks for understanding, scripted transitions) is skipped.

**Fix:**
1. After compilation (line ~284), call `LLMClient.review_lesson_package()` with the generated MasterContent JSON.
2. Merge the review result into `GenerationReport`.
3. If review returns `passed: False`, include the issues in the response to the teacher.
4. Do NOT block delivery on review failure (matches NLAH Stage 4: "Non-blocking: low scores logged as warnings").

**Effort:** ~1 hour

---

### P1-4: Voice match scoring stub

**Problem:** NLAH Section 4 defines `score_voice_match(lesson_text, persona_context) → float` adapter. No implementation exists. NLAH Stage 4 includes: "Verifier runs LLM voice-match score against teacher persona" with gate "score >= 3.0/5.0".

**Fix:**
1. Add `score_voice_match()` to `clawed/quality.py` — a single LLM call that returns a 1.0-5.0 float.
2. Wire into `generate_lesson_bundle.py` after quality review.
3. Log as `VOICE_MISMATCH` warning if score < 3.0; do not block delivery (NLAH: "do not block delivery").
4. Include score in `GenerationReport`.

**Effort:** ~1 hour

---

### P1-5: extract _run_async_safe to shared utility

**Problem:** `_run_async_safe()` is duplicated in both `export_pptx.py:112-127` and `export_docx.py:26-37`. NLAH migration path flags `export_pptx.py (nested asyncio.run in thread)` as a replacement target.

**Fix:** (Part of P0-3, listed separately for tracking)
1. Create `clawed/async_utils.py` with `run_async_safe(coro)`.
2. Update all three call sites: `export_pptx.py`, `export_docx.py`, `generation.py`.

**Effort:** Included in P0-3.

---

### P1-6: Hardcoded SOUL.md path

**Problem:** `clawed/lesson.py:25-26` hardcodes `Path.home() / ".eduagent" / "workspace" / "SOUL.md"`. Also duplicated in `clawed/agent_core/core.py:342-344`. NLAH Section 8 migration path flags: "lesson.py SOUL.md hardcoded path → Persona Reader (uses AppConfig)".

**Fix:**
1. Add `workspace_dir` property to `AppConfig` (or use existing `EDUAGENT_DATA_DIR` env var resolution).
2. Replace both hardcoded paths with `config.workspace_dir / "SOUL.md"`.

**Effort:** ~30 minutes

---

## Test Additions Required

### New tests for P0 items:

| Test | File | What it covers |
|------|------|---------------|
| `test_bundle_persona_failure_logged` | `tests/test_bundle.py` | TeacherPersona(**bad_data) produces warning in report, not silent pass |
| `test_bundle_kb_failure_logged` | `tests/test_bundle.py` | KB search exception surfaces in GenerationReport.warnings |
| `test_bundle_asset_failure_logged` | `tests/test_bundle.py` | Asset search exception surfaces in GenerationReport.warnings |
| `test_review_fails_closed_on_llm_error` | `tests/test_quality_review.py` | `review_lesson_package()` returns `passed: False` when `generate()` raises |
| `test_review_fails_closed_on_missing_key` | `tests/test_quality_review.py` | Result without `passed` key returns `passed: False` |
| `test_run_async_safe_no_loop` | `tests/test_async_utils.py` | `run_async_safe()` works from sync context |
| `test_run_async_safe_nested` | `tests/test_async_utils.py` | `run_async_safe()` works from inside running event loop |
| `test_demo_mode_env_override` | `tests/test_demo.py` | `CLAWED_DEMO=1` forces demo mode even with stored key |
| `test_demo_mode_stored_key` | `tests/test_demo.py` | Stored key (no env var) correctly disables demo mode |
| `test_onboard_name_truncation` | `tests/test_onboarding.py` | Names > 100 chars are truncated |
| `test_onboard_grade_validation` | `tests/test_onboarding.py` | Non-numeric, non-K grades are rejected with re-prompt |
| `test_onboard_workspace_failure_logged` | `tests/test_onboarding.py` | `init_workspace` failure is logged, not silently swallowed |

### New tests for P1 items:

| Test | File | What it covers |
|------|------|---------------|
| `test_failure_codes_enum` | `tests/test_failure_codes.py` | All 10 NLAH codes exist and are strings |
| `test_nlah_guided_notes_gate` | `tests/test_validation.py` | MasterContent with < 6 guided notes fails validation |
| `test_nlah_primary_sources_gate` | `tests/test_validation.py` | MasterContent with < 2 sources fails validation |
| `test_nlah_exit_ticket_gate` | `tests/test_validation.py` | MasterContent with < 3 exit ticket questions fails validation |
| `test_nlah_topic_drift_gate` | `tests/test_validation.py` | Topic not in title/aim triggers TOPIC_DRIFT |
| `test_voice_match_score` | `tests/test_quality.py` | `score_voice_match()` returns float 1.0-5.0 |
| `test_quality_review_in_bundle` | `tests/test_bundle.py` | Bundle pipeline calls review_lesson_package and includes results |

---

## CHANGELOG.md Changes

Add a new section at the top:

```markdown
## [2.3.8] - 2026-03-XX

NLAH contract alignment — explicit failures replace silent swallowing, quality gates fail closed.

### Added
- **NLAH failure taxonomy** — 10 structured failure codes (NO_PERSONA, SCHEMA_ERROR, TOPIC_DRIFT, etc.) as `FailureCode` enum in `clawed/failure_codes.py`. All generation failures now report machine-parseable codes.
- **`CLAWED_DEMO=1` env var** — force demo mode regardless of stored API keys. Fixes stored-key vs env-var detection confusion.
- **Voice match scoring** — `score_voice_match()` in `clawed/quality.py` scores lesson text against teacher persona (1.0-5.0). Logged as VOICE_MISMATCH warning if < 3.0.
- **`run_async_safe()` shared utility** — extracted from duplicated code in `export_pptx.py` and `export_docx.py` to `clawed/async_utils.py`.

### Changed
- **Quality review fails closed** — `review_lesson_package()` now catches all exceptions (including LLM call failures) and returns `passed: False`. Previously, LLM errors propagated uncaught, skipping the quality gate entirely.
- **Silent exceptions → explicit warnings** — `generate_lesson_bundle.py` now logs persona parse failures, KB search failures, and asset search failures at WARNING level and includes them in the quality notes returned to the teacher.
- **Onboarding input validation** — teacher name truncated to 100 chars, grade validated as K/PK/1-12, subject truncated to 100 chars. Workspace init failures logged instead of silently swallowed.
- **NLAH validation gates enforced** — MasterContent validation now checks guided_notes >= 6, primary_sources >= 2, exit_ticket questions >= 3, and topic presence in title/aim.

### Fixed
- **Nested asyncio.run() in background ingest** — `generation.py` background thread now uses `run_async_safe()` instead of bare `asyncio.run()`, preventing RuntimeError on Python 3.12+.
- **Demo mode with stored keys** — `CLAWED_DEMO=1` environment variable provides explicit override for demo mode activation.
- **SOUL.md hardcoded path** — `lesson.py` and `agent_core/core.py` now use `AppConfig` workspace path instead of hardcoded `~/.eduagent/workspace/SOUL.md`.
```

---

## ROADMAP.md Changes

Add a new section after the v2.3.3 Quality Layer block:

```markdown
## v2.3.8 -- NLAH Contract Alignment

Explicit failure handling, fail-closed quality gates, async cleanup.

- [x] NLAH failure taxonomy — 10 structured failure codes
- [x] Quality review fails closed (not silently open)
- [x] Silent exception swallowing replaced with explicit warnings
- [x] Nested asyncio.run() fixed in background threads
- [x] Demo mode env var override (CLAWED_DEMO=1)
- [x] Onboarding input validation
- [x] NLAH validation gates for MasterContent
- [x] Voice match scoring stub
- [x] SOUL.md path from config (not hardcoded)
```

---

## Execution Order

1. **P0-3** first (async_utils.py extraction) — creates shared utility needed by other changes
2. **P0-2** (quality review fails closed) — smallest, highest-impact fix
3. **P0-1** (failure taxonomy in bundle) — depends on understanding GenerationReport
4. **P0-4** (demo mode env override) — standalone, quick
5. **P0-5** (onboarding validation) — standalone, quick
6. **P1-1** (failure codes enum) — sets up structured codes for P1-2
7. **P1-2** (NLAH validation gates) — depends on P1-1
8. **P1-3** (quality review in bundle) — depends on P0-2
9. **P1-4** (voice match scoring) — depends on P1-3
10. **P1-6** (SOUL.md path) — standalone cleanup

Tests should be written alongside each item (TDD where practical).

---

## Claude Code Review (2026-03-30)

**Overall Rating: NEEDS_REVISION**

The plan is well-structured, correctly identifies real bugs, and proposes sound fixes. However, there are several inaccuracies in line references, one factual error in P1-2, a sequencing problem in P0-1, and missing context about test file targeting. All fixable — nothing requires rethinking the approach.

---

### P0-1: Failure taxonomy in generate_lesson_bundle — **CONFIRMED with caveats**

**Line numbers verified:**
- Lines 96-99: `TeacherPersona(**context.persona)` with bare `except Exception: pass` — CONFIRMED.
- Lines 118-130: AssetRegistry search with `logger.debug` at line 130 — CONFIRMED.
- Lines 133-165: CurriculumKB search with `logger.debug` at line 165 — CONFIRMED.
- Lines 207-208: MasterContent generation failure returning raw exception string — CONFIRMED.

**Sequencing problem:** The fix says "append to `GenerationReport.warnings`" for the persona failure at line 99, but `GenerationReport()` is not instantiated until line 214. The persona/KB/asset search all happen *before* the report exists. Fix: either (a) move `report = GenerationReport()` to the top of `execute()`, before line 92, or (b) accumulate warnings in a temporary `pre_report_warnings: list[str]` and drain them into the report after line 214.

**Overlap with P1-1:** Step 3 says "Define failure codes as constants" but P1-1 creates the `FailureCode` enum later in execution order. Clarify: P0-1 should use plain string literals (e.g., `"PERSONA_PARSE_ERROR"`) and P1-1 refactors them into the enum. Or move P1-1 before P0-1 in execution order.

---

### P0-2: Quality review fails closed — **CONFIRMED**

**Line numbers verified:**
- `review_lesson_package()` at lines 407-445 — CONFIRMED.
- `self.generate()` call at line 435 is OUTSIDE the try/except (lines 436-445) — CONFIRMED.
- Only JSON parse errors are caught, not LLM call failures — CONFIRMED.

**Important context the plan should add:** The v2.3.5 changelog already says "Quality review fails closed — `review_lesson_package()` returns `passed: False` on parse errors instead of silently passing." That fix handled *parse* errors (lines 436-445). This P0-2 fix handles *LLM call* errors (line 435). The plan should explicitly note this is completing the v2.3.5 fix, not contradicting it.

**Proposed code:** The `"passed" not in result` guard is a good addition beyond what was described in the problem statement. Code looks correct.

---

### P0-3: Nested asyncio.run() in background ingest thread — **CONFIRMED**

**Line numbers verified:**
- `asyncio.run(extract_persona(docs, persona_cfg))` at generation.py:632 — CONFIRMED.
- Thread spawned at generation.py:649 — CONFIRMED.
- `_run_async_safe()` in export_pptx.py:112-127 — CONFIRMED.
- Identical duplicate in export_docx.py:22-37 — CONFIRMED.

**Minor note:** The plan says the thread is at line 649. Actual code: `t = threading.Thread(target=_bg_ingest, daemon=True)`. The `daemon=True` flag means the thread can be killed mid-write on process exit — potential data loss in the persona save at line 633-634. Out of scope for NLAH but worth a future TODO.

---

### P0-4: Demo mode env override — **CONFIRMED**

**Line numbers verified:**
- `is_demo_mode()` at demo/__init__.py:34-44 — CONFIRMED.
- `resolve_credentials()` at config.py:98-121 — CONFIRMED.
- Proposed code is clean and correct.

No issues.

---

### P0-5: Onboarding state write protection — **CONFIRMED with minor line ref corrections**

**Line numbers verified:**
- `state["name"] = text.strip()` at onboard.py:113 — CONFIRMED.
- Grade fallthrough at onboard.py:106 (`state["grade"] = text.strip()`) — CONFIRMED.
- Subject at onboard.py:87 — CONFIRMED.
- `init_workspace` silent `pass` at onboard.py:135-136 — CONFIRMED.
- `_complete_onboarding` at onboard.py:118-147 — CONFIRMED.

**Existing coverage note:** `tests/test_onboarding_safety.py` already tests `TeacherProfile` model-level truncation (`test_name_truncated_at_100`). The P0-5 fix adds handler-level validation *before* the model, which is correct (defense in depth), but the plan should acknowledge the existing model-level guard to avoid duplicate test confusion.

**Location ref:** Plan says "Location: `clawed/handlers/onboard.py:112-136`" but `_complete_onboarding` starts at line 118. The grade validation happens at line 99-106 in the `step()` method, not in `_complete_onboarding`. The grade re-prompt logic needs to go in `step()`, not `_complete_onboarding()`.

---

### P1-1: NLAH failure taxonomy enum — **CONFIRMED**

No issues. Clean standalone task.

---

### P1-2: MasterContent validation gates — **INACCURATE (partial)**

**Topic drift check already exists:** The plan says "No check: topic appears in title or aim (TOPIC_DRIFT gate)" but `validate_master_content()` at validation.py:38-39 already checks `if topic.lower() not in mc.title.lower() and topic.lower() not in mc.topic.lower()`. This check exists — it just doesn't use the NLAH failure code and doesn't check the `aim` field specifically. The plan should say "topic drift check exists but needs to be extended to check `aim` and use NLAH failure codes."

**Threshold gaps are real:**
- Current: `guided_notes < 1` → NLAH wants `>= 6`. CONFIRMED gap.
- Current: `exit_ticket < 1` → NLAH wants `>= 3`. CONFIRMED gap.
- Current: `primary_sources < 1` → NLAH wants `>= 2` with non-empty `text`. CONFIRMED gap.

**Retry loop:** The plan correctly identifies the missing retry-on-CRITICAL loop. This is the most complex part of P1-2 and should get its own effort estimate — the current "~2 hours" may be tight if the retry needs to inject issues into the prompt and handle the generate_master_content call path.

---

### P1-3: Quality review integration — **CONFIRMED**

- `generate_lesson_bundle.py` never calls `review_lesson_package()` — CONFIRMED.
- `GenerationReport` has `quality_review_passed` and `quality_review_issues` fields but they're never populated in the bundle pipeline — CONFIRMED.
- Placement after compilation (~line 284) is correct.

---

### P1-4: Voice match scoring stub — **CONFIRMED**

- `clawed/quality.py` exists with `LessonQualityScore` — correct target file.
- `GenerationReport` already has `voice_check_passed` and `voice_check_issues` fields — wiring is straightforward.

---

### P1-5: extract _run_async_safe — **CONFIRMED**

Correctly identified as part of P0-3. Line numbers match.

---

### P1-6: Hardcoded SOUL.md path — **CONFIRMED**

- lesson.py:25-26: `Path.home() / ".eduagent" / "workspace" / "SOUL.md"` — CONFIRMED.
- agent_core/core.py:342: same hardcoded path — CONFIRMED.

---

### Test File Targeting Issues

The plan proposes tests in files that don't exist and misses existing files:

| Plan target | Actual state | Recommendation |
|------------|-------------|----------------|
| `tests/test_bundle.py` | Does NOT exist. `tests/test_bundle_integration.py` exists. | Add to `test_bundle_integration.py` or create `test_bundle.py` (clarify which). |
| `tests/test_quality_review.py` | Does NOT exist. | Must be created — plan should note this. |
| `tests/test_async_utils.py` | Does NOT exist. | Must be created — plan should note this. |
| `tests/test_onboarding.py` | EXISTS but tests `clawed/onboarding.py` (CLI wizard), not `clawed/handlers/onboard.py` (handler). | Use `tests/test_onboarding_safety.py` (already tests OnboardHandler's model) or create `tests/test_onboard_handler.py`. |
| `tests/test_demo.py` | EXISTS — can add tests here. | Correct. |
| `tests/test_validation.py` | Does NOT exist. | Must be created. |
| `tests/test_failure_codes.py` | Does NOT exist. | Must be created. |
| `tests/test_quality.py` | Does NOT exist. | Must be created. |

---

### Missed Items Worth Including

1. **`GenerationReport` instantiation timing** (see P0-1 caveat above) — this is a blocker for P0-1 as written. The report must be created before the persona/KB/asset blocks to collect their warnings.

2. **v2.3.5 changelog overlap for P0-2** — the plan should acknowledge that v2.3.5 partially fixed this (parse errors) and v2.3.8 completes it (LLM call errors). Otherwise someone reading the changelog sees "fails closed" claimed twice.

3. **`review_lesson_package` missing `"passed" not in result` guard in current code** — the existing code at llm.py:443 does `return json.loads(cleaned)` without checking that the parsed JSON actually contains a `"passed"` key. If the LLM returns valid JSON without that key (e.g., `{"result": "ok"}`), the caller would get a dict without `"passed"`, which violates fail-closed. The proposed code in P0-2 correctly adds this guard, but it should be called out as a separate bug in the problem statement.

4. **No test for the onboard handler's grade fallthrough** — the plan tests "Non-numeric, non-K grades are rejected with re-prompt" but the fix is in `step()` (line 106), not `_complete_onboarding()`. The test needs to call `OnboardHandler.step()` through the ASK_GRADE state, not just test `_complete_onboarding`.

---

### Sequencing Corrections

The proposed execution order is mostly correct. Two adjustments:

1. **Consider P1-1 before P0-1** — P0-1 step 3 defines ad-hoc failure code constants that P1-1 immediately replaces with an enum. Building the enum first avoids throwaway work. If you want P0 items first for release safety, then P0-1 step 3 should explicitly say "use string literals; P1-1 will replace them."

2. **P1-3 should note it needs an `LLMClient` instance** — `generate_lesson_bundle.py` currently doesn't instantiate `LLMClient`. The `config` is available via `context.config`, but the plan should note that a client must be created (or injected via context) for the `review_lesson_package()` call.

---

### Final Recommendation

**NEEDS_REVISION** — but revisions are minor. Specifically:

1. Fix the `GenerationReport` instantiation timing problem in P0-1 (blocker).
2. Correct the P1-2 topic drift claim (it already exists, just needs NLAH code + aim check).
3. Clarify test file targets (6 of 8 proposed test files don't exist yet).
4. Add a note about P0-2's relationship to the v2.3.5 fix.
5. Decide on P0-1/P1-1 sequencing for failure code constants vs enum.

After those edits, this plan is SHIP_READY. The bugs are real, the fixes are correct, the execution order is sound, and the scope is appropriately bounded.
