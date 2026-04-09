# Claw-ED v2.3.6 Plan — Hardening & Infrastructure

**Date:** 2026-03-29
**Theme:** Fix what's fragile — security, concurrency, performance, dead weight, test coverage.
**Sources:** v2.3.5 audit (8 remaining issues), v2.3.5 deferred items, Sirhan/Windows testing feedback.

---

## Practical Reality Check (from testing)

1. **The LLM is the bottleneck.** minimax-m2.7:cloud timed out at 90s trying to generate MasterContent JSON (18 fields, nested sub-models). Everything downstream — teacher doc, student doc, slides — is only as good as that one JSON blob. MasterContent needs a DEEP-tier model, not WORK-tier.

2. **Ingestion is the biggest UX problem.** 20+ minutes of "typing..." with no feedback while it chews through 14K files / 102GB. A real teacher gives up. Needs background threading with progress updates ("Indexed 347/500 files...").

3. **Structural validators != pedagogical quality.** The 10 validators check "are guided notes present?" but can't evaluate "does this Do Now actually activate prior knowledge?" That gap only closes with teacher feedback + the memory loop in real classroom use.

4. **Voice matching depends on corpus quality.** Whether lessons sound like *you* vs. generic-teacher-who-teaches-Social-Studies depends on how much signal is in the curricula files and how well the LLM interprets it. More files + better model = better results.

**Bottom line:** The architecture is right. The value prop is compelling. But it needs a stronger model for generation, background ingestion, and real classroom iteration. ~70% of the way from working prototype to daily tool.

---

## Release Bar

Ship v2.3.6 when Phases 1-3 pass. Phase 4 is strongly recommended.
Phase 5 items are quality-of-life improvements that can ship incrementally.

---

## Phase 0: The Bottleneck — Model Routing for MasterContent

**Why:** This is the single highest-impact change. MasterContent is the most complex JSON structure in the system (18 fields, 8 nested sub-model types). The WORK-tier model (minimax-m2.7:cloud) times out at 90s and produces thin content. Moving this to DEEP tier with a capable model transforms output quality overnight.

### Task 0.1: Add master_content task type to model router
**Files:** `clawed/model_router.py:26-48`
**Fix:** Add `master_content` to the DEEP tier:
```python
TASK_TIERS: dict[str, ModelTier] = {
    # ...existing entries...
    # Deep tier
    "persona_extract": ModelTier.DEEP,
    "evaluation": ModelTier.DEEP,
    "master_content": ModelTier.DEEP,  # NEW — structured JSON needs a strong model
}
```

### Task 0.2: Use master_content task type in generate_master_content()
**Files:** `clawed/lesson.py` (generate_master_content function)
**Fix:** Change the `task_type` default from `"lesson_plan"` to `"master_content"`:
```python
async def generate_master_content(
    ...
    task_type: str = "master_content",  # was "lesson_plan"
    ...
```

### Task 0.3: Recommend model upgrade in docs
**Files:** `README.md` or new `docs/MODEL_GUIDE.md`
**Fix:** Document which models work well for MasterContent generation:
- **Best:** Claude Sonnet 4.5+ (fast, excellent structured JSON)
- **Good:** GPT-4o, Gemini 2.5 Pro (reliable JSON, good pedagogy)
- **Acceptable:** minimax-m2.7:cloud (works for simple lessons, times out on complex topics)
- **Not recommended:** Small local models (qwen3.5:9b, etc.) — can't handle 18-field schema

### Task 0.4: Increase safe_generate_json timeout for MasterContent
**Files:** `clawed/llm.py` (generate method)
**Problem:** Default HTTP timeout may be 60-90s. MasterContent with a cloud model can take 30-60s legitimately.
**Fix:** Check the httpx timeout in the LLM client. If it's under 120s, bump to 180s for MasterContent-class generations. Or make it configurable via AppConfig.

**Commit:** `fix: route MasterContent to DEEP tier — structured JSON needs a strong model`

---

## Phase 1: Security & Correctness — BLOCKER

### Task 1: Path traversal in read_workspace tool
**Files:** `clawed/agent_core/tools/read_workspace.py:42-44`
**Problem:** `target = workspace / filename` — no `../` validation. An LLM-injected filename like `../../.ssh/id_rsa` reads arbitrary files.
**Fix:**
```python
target = (workspace / filename).resolve()
if not str(target).startswith(str(workspace.resolve())):
    return ToolResult(text="Access denied: filename must be within workspace.")
```

### Task 2: TOOL_DEFINITIONS monkey-patching (concurrency bug)
**Files:** `clawed/agent_core/core.py:48-69`, `clawed/agent.py:79-86,176-177,246-248`
**Problem:** `_agent_mod.TOOL_DEFINITIONS = tools` mutates a module-level global with no locking. Concurrent async requests can read another teacher's tool definitions.
**Fix:**
- Refactor `_call_with_native_tools(messages, system, config)` and `_call_with_ollama_tools(messages, system, config)` in `agent.py` to accept a `tools: list[dict]` parameter.
- Pass tools explicitly instead of monkey-patching the global.
- Remove the try/finally swap pattern from `core.py`.

### Task 3: YouTube URL deduplication by video ID
**Files:** `clawed/asset_registry.py:234-236`
**Problem:** `eu.url not in youtube_urls` compares raw URL strings. Same video with different URL forms (`youtube.com/watch?v=X` vs `www.youtube.com/watch?v=X` vs `youtu.be/X`) creates duplicates.
**Fix:**
```python
# Before adding extraction URLs, normalize to video IDs
existing_ids = set(extract_youtube_ids(url)[0] for url in youtube_urls if extract_youtube_ids(url))
for eu in extraction.urls:
    if eu.link_type == 'youtube':
        eu_ids = extract_youtube_ids(eu.url)
        if eu_ids and eu_ids[0] not in existing_ids:
            youtube_urls.append(f"https://youtube.com/watch?v={eu_ids[0]}")
            existing_ids.add(eu_ids[0])
```

### Task 4: ingest_materials tool file cap
**Files:** `clawed/agent_core/tools/ingest_materials.py`
**Problem:** Handler enforces 500-file cap, but the tool doesn't — direct tool calls bypass the guard.
**Fix:** Add file count check at the top of `execute()` before calling `ingest_path()`.

**Commit:** `fix: security hardening — path traversal, tool isolation, URL dedup, ingest cap`

---

## Phase 2: Performance & Stability — BLOCKER

### Task 5: Background ingestion with progress updates
**Files:** `clawed/handlers/ingest.py:22-118`, `clawed/transports/telegram.py`
**Problem:** Ingestion runs synchronously in the async handler. 14K files / 102GB = 20+ minutes of "typing..." with no feedback. Teachers give up. This is the #1 UX blocker.
**Fix (three parts):**

**5a: Move ingestion to background thread**
```python
async def handle(self, teacher_id, files):
    # Start ingest in background, return immediately
    task = asyncio.create_task(self._ingest_background(teacher_id, files))
    return GatewayResponse(text="Starting ingestion — I'll update you as I go.")

async def _ingest_background(self, teacher_id, files):
    # Run blocking work in thread pool
    result = await asyncio.to_thread(self._do_ingest, teacher_id, files)
    # Send completion message back via transport
    await self._notify(teacher_id, result)
```

**5b: Progress callbacks during file processing**
```python
# In the file processing loop:
for i, file_path in enumerate(all_files):
    if i % 50 == 0:
        await self._notify(teacher_id, f"Indexed {i}/{len(all_files)} files...")
    # ... process file ...
```

**5c: KB indexing in thread pool**
```python
chunks_added = await asyncio.to_thread(kb.index, teacher_id=teacher_id, ...)
```

### Task 6: TF-IDF unbounded vocabulary growth
**Files:** `clawed/agent_core/memory/embeddings.py:62-100`
**Problem:** `self._vocab` dict grows with every unique token seen. After 50K unique tokens, embedding vectors become 50K-dimensional. Memory bloat + cosine similarity slowdown.
**Fix:**
```python
MAX_VOCAB_SIZE = 10_000

def embed(self, text: str) -> list[float]:
    tokens = self._tokenize(text)
    for t in tokens:
        if t not in self._vocab and len(self._vocab) < MAX_VOCAB_SIZE:
            self._vocab[t] = self._next_idx
            self._next_idx += 1
    # Tokens not in vocab are silently ignored (OOV)
    vec = [0.0] * MAX_VOCAB_SIZE  # Fixed-size vector
    ...
```

### Task 7: Remove unused anthropic/openai dependencies
**Files:** `pyproject.toml:31-32`
**Problem:** `anthropic>=0.40.0` and `openai>=1.0.0` declared as dependencies but never imported. All API calls use raw `httpx`. Adds ~200KB + 15 transitive deps to every install.
**Fix:** Remove both from `[project] dependencies`. If needed for future SDK migration, add to `[project.optional-dependencies] sdk`.

**Commit:** `fix: performance — async ingest, vocab cap, remove dead deps`

---

## Phase 3: Testing & CI — HIGH

### Task 8: CI workflow
**Files:** new `.github/workflows/ci.yml`
**Fix:** Create GitHub Actions workflow:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: python -m pytest tests/ -q --cov=clawed --cov-fail-under=55
```

### Task 9: Critical module test coverage
**Files:** new test files for the 6 most critical untested modules:
- `tests/test_llm_client.py` — API routing, model selection, demo mode, retry logic
- `tests/test_database_ops.py` — CRUD operations, migrations, schema versioning
- `tests/test_tools_dispatch.py` — Tool execution paths, parameter validation
- `tests/test_persona_extraction.py` — Name extraction, field validation
- `tests/test_standards_lookup.py` — State standards resolution, format helpers
- `tests/test_export_pipeline.py` — DOCX/PPTX/PDF export with mock content

Target: raise coverage floor from 55% to 65%.

### Task 10: Lightweight DB migration framework
**Files:** `clawed/database.py`
**Problem:** Manual one-off ALTER TABLE statements. No version tracking. Hard to collaborate on schema changes.
**Fix:**
```python
MIGRATIONS = [
    (1, "ALTER TABLE lessons ADD COLUMN scores_json TEXT"),
    (2, "ALTER TABLE ..."),
]

def _run_migrations(self, conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INT)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row[0] else 0
    for version, sql in MIGRATIONS:
        if version > current:
            conn.execute(sql)
            conn.execute("INSERT INTO schema_version VALUES (?)", (version,))
    conn.commit()
```

**Commit:** `feat: CI pipeline, critical module tests, DB migration framework`

---

## Phase 4: Quality of Life — MEDIUM

### Task 11: Image embedding in student DOCX
**Files:** `clawed/compile_student.py`
**Problem:** Student DOCX doesn't embed images from the MasterContent image_specs. Teacher DOCX and PPTX do.
**Fix:** Use the `images` dict (already passed to `compile_student_view`) to embed images alongside primary source text and instruction content.

### Task 12: Visual source density enforcement
**Files:** `clawed/prompts/master_content.txt`
**Problem:** The prompt says images are optional (`image_spec: str = ""`). For subjects like Science and Social Studies, every primary source and instruction section should have an image_spec.
**Fix:** Add subject-conditional image requirement:
```
For Science and Social Studies lessons: every primary_source and every
instruction section MUST have a non-empty image_spec describing an
appropriate academic image.
```

### Task 13: Output directory consistency
**Files:** `clawed/agent_core/tools/generate_lesson_bundle.py:294`
**Problem:** Hardcoded `Path("clawed_output")` fallback. Should always use `config.output_dir`.
**Status:** Partially addressed in v2.3.5 (bundle tool checks config.output_dir). Verify all other CLI commands also respect it.

### Task 14: Few-shot example length
**Files:** `clawed/corpus.py`
**Problem:** Few-shot examples capped at 2000 chars — rich examples get truncated before the LLM sees them.
**Fix:** Raise cap to 4000 chars. The MasterContent prompt has headroom since we eliminated persona double-injection.

**Commit:** `feat: student images, source density, output dir, few-shot length`

---

## Implementation Order

```
Phase 0 (model routing) ── HIGHEST ─── do first, biggest impact
Phase 1 (security)       ── BLOCKER ─── must ship
Phase 2 (performance)    ── BLOCKER ─── must ship
Phase 3 (testing/CI)     ── HIGH ────── should ship
Phase 4 (quality)        ── MEDIUM ──── should ship
Phase 5 (quality-of-life)── MEDIUM ──── nice to have
```

Phase 0 is a 2-line change with massive impact — do it first.
Phases 1-2 are independent and can be worked in parallel.
Phase 3 depends on Phase 2 (dep removal affects CI setup).
Phase 4-5 depend on nothing.

---

## Estimated Scope

- **Phase 0 (do first):** 2 files, ~5 lines — instant quality upgrade
- **Phases 1-2 (must ship):** ~10 files modified, ~300 lines changed
- **Phase 3 (should ship):** ~8 files added/modified, ~500 lines
- **Phases 4-5 (nice to have):** ~6 files modified, ~250 lines

---

## Verification Plan

1. `ruff check .` — zero violations
2. `python -m pytest tests/ -q --cov=clawed` — all pass, coverage >= 55% (65% if Phase 3 ships)
3. Security check:
   - `read_workspace("../../etc/passwd")` → "Access denied"
   - Concurrent lesson generation doesn't leak tool definitions
4. Performance check:
   - Ingest 100 files via Telegram — bot remains responsive during indexing
   - TF-IDF embedder stays under 10K vocab after ingesting 1000 documents
5. Sirhan smoke test:
   - All 16 v2.3.5 tests still pass
   - YouTube links deduplicated (same video, different URL forms → 1 link)
