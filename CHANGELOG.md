# Changelog

## v6.19.2026.2 — 2026-06-19

### Fixed — Lesson deck density + title-slide layout (real-content fixes)

- A real generated lesson exposed slide types the fixtures missed: the station
  overview dumped every station's full directions (~105 words/slide), exit
  tickets ran long, long source titles bloated headers. Capped so even a
  content-rich deck stays ~18 words/slide (max ~30).
- Fixed the title slide: long lesson names auto-shrink (42/34/28pt) and the
  meta/objective reposition with clearance instead of overlapping the title.

## v6.19.2026.1 — 2026-06-19

### Improved — Lesson slide decks (sparse, image-forward, exemplar-matched)

- Reworked the deck builder (compile_slides.py / export_pptx.py) to a sparse,
  image-forward 16:9 deck (~15-18 words/slide instead of paragraph dumps) on the
  standard 10x5.625in canvas that opens cleanly on macOS and imports losslessly
  into Google Slides. Aspect-ratio-preserving image grid (no stretch), Century
  Gothic look, Turn-and-Talk + image-activity slides, and an optional Drive
  upload that converts the deck to native Google Slides.

### Fixed — Agent loop crash on empty model turns

- save_turn no longer crashes with "TypeError: 'NoneType' object is not
  subscriptable" when the model returns a tool-only or empty turn (seen with
  some OpenRouter models); content is coerced to "" before slicing.

## v6.19.2026 — 2026-06-19

### Added — Optional support funnel at CLI + landing

- Surfaced an optional, free-forever-respecting "support the project"
  link (macxlabs.app/support) at both `clawed setup` completion panels
  and on the landing page (support section + footer). The support rail
  offers recurring monthly tiers; all links carry `?src` tags for
  conversion measurement. No paywall — Claw-ED remains free.

## v6.18.2026 — 2026-06-18

### Fixed — Memory and Embeddings

- The local TF-IDF fallback embedder is now stateless and deterministic
  (feature hashing into a fixed 512-dimensional space). Previously it grew a
  per-instance vocabulary that was never persisted, so curriculum-search
  embeddings silently became incompatible across process restarts and could
  crash the search matmul when a query was longer than the indexed documents.
- `get_embedder()` falls back cleanly to the TF-IDF embedder when the ONNX
  MiniLM model cannot be downloaded, instead of returning a non-functional one.
- Curriculum KB search pads to the larger of the query/document dimension for
  robustness with mixed-dimension stores.

### Changed

- The landing page and first-run setup now point teachers who don't use the
  command line to the hosted, done-for-you option.

## v5.15.2026 — 2026-05-15

### Hardened — Filesystem Boundaries and Release Trust

- Replaced unsafe string-prefix path containment checks with
  boundary-aware `Path.relative_to()` containment through
  `clawed.paths.path_is_within()`.
- Hardened self-modification reads/writes, workspace reads, output file
  listing/organization, and material ingestion against prefix-sibling path
  escapes such as `/tmp/workspace-evil` being treated as inside
  `/tmp/workspace`.
- Moved API token path resolution from an import-time constant to
  `clawed.paths.api_token_path()` so `EDUAGENT_DATA_DIR` changes are honored
  at runtime.
- Fixed a stale Telegram daemon setup hint so it points to the real
  `clawed config set-token YOUR_TOKEN` command.
- Updated architecture and security documentation to reflect the current
  Python 3.11+ requirement, filesystem boundary layer, and non-certified
  compliance posture.

### Verified

- `uv run --extra dev ruff check ...`: clean for changed source and tests.
- `uv run --extra dev mypy --strict clawed`: 0 errors.
- `uv run --extra dev python -m pytest -q tests/test_audit_fixes.py tests/test_file_manager.py tests/test_security.py`: 50 passed.

## v4.25.2026 — 2026-04-25

### Hardened — Release, Security, and Publish Readiness

- Removed vulnerable base `requests` dependency. Telegram now uses `urllib3`
  directly for the Windows-compatible transport path, and model discovery uses
  the existing `httpx` dependency.
- Moved Google text-to-speech behind the optional `tts` extra so the base
  install stays smaller and easier to audit.
- Upgraded the locked dependency graph and verified `pip-audit` reports no
  known vulnerabilities in the synced development environment.
- Fixed PDF/export dependency pins: `pypdf` now targets the patched 6.x line,
  and broken `reportlab` 4.4.10 is excluded.
- Added strict typing to CI and kept `mypy --strict clawed` passing across all
  270 Python source files.
- Added wheel CLI smoke testing in CI so stale bundled CLI assets cannot ship a
  mismatched `clawed --version`.
- Reworked local release scripts to use `uv build` / `uv publish`, support the
  project’s numeric release schemes, and bump `clawed/__init__.py` instead of
  the legacy `eduagent` shim.

### Verified

- 2092 tests passing, 4 skipped.
- `ruff check .`: clean.
- `mypy --strict clawed`: 0 errors.
- Built wheel and sdist; installed wheel reports `4.25.2026 (Claw-ED)`.

## v4.16.2026.0 — 2026-04-16

### Hardened — Type Safety & Exception Chaining

- **`mypy --strict` passes on all 270 source files, zero errors.** The previous
  lax config (`check_untyped_defs = true` only) allowed 229 real type errors
  and 845 unchecked annotations. Strict mode is now enforced project-wide.
- **1074 → 0 mypy strict errors across 144 files.** Work divided into 8 parallel
  subagent batches covering `clawed/api/`, `clawed/agent_core/`, all
  `clawed/commands/`, `clawed/transports/`, exports, generation hot path, and
  handlers. Only narrow `# type: ignore[<code>]` annotations with inline
  justifications retained — no blanket ignores.
- **Real runtime bugs caught and fixed by the strict pass:**
  - `clawed/generation.py:207` imported `generate_materials` from
    `clawed.materials`, but the real name is `generate_all_materials`. Any call
    to `handle_generate_materials` would have raised `ImportError`.
  - `clawed/generation.py:550` accessed `.get('code')` / `.get('description')`
    on tuples returned by `get_standards()`. Runtime `AttributeError` on first
    use. Replaced with tuple indexing.
  - `clawed/commands/drive.py` called async `DriveClient.list_files` and
    `read_file` synchronously in three places. Wrapped with `run_async(...)`.
  - `clawed/commands/generate_ingest.py` passed `old_persona=None` to
    `persona_evolution.record_ingestion_changes` on first-run ingest, violating
    the signature. Guarded with a None check.
  - `clawed/commands/config_profile.py` `_standards_json` accessed `.code` /
    `.description` on `get_standards()` tuples; fixed with unpacking. The
    `qrcode.make(...).save(output)` call now passes a binary file handle.
  - `clawed/_entry_router.py:602-603` assigned a `CompletedProcess[bytes]` to
    a `str` variable, then called `.returncode` on the str. Fixed by binding
    `proc` and deriving the string separately.
  - Missing None guards in `commands/_helpers.py::load_persona_or_exit` and
    several persona-load sites added.
- **Pydantic `field_validator` methods, FastAPI route signatures, Typer command
  callbacks, and context-manager helpers all carry explicit types** for the
  first time. Pydantic generic types, `Awaitable[T] → T` async helpers, and
  `AsyncGenerator` event streams get concrete annotations.
- **B904 suppression removed.** All 51 `raise X(...)` sites inside `except`
  blocks now chain the original exception with `from <exc>`, preserving the
  traceback chain. Bare `except ClassName:` clauses gained `as e:` bindings
  where required. No `from None` used — every chain is preserved.
- **Third-party type stubs added:** `types-PyYAML`, `types-requests`,
  `types-python-dateutil`, `types-reportlab`, `types-qrcode`, `types-pytz`.
  Narrow `ignore_missing_imports` overrides for genuinely-untyped deps
  (anthropic, apscheduler, faster_whisper, google.*, manim, textual, etc.).

### Verified — April 2026 Audit Remediation Regression Pass

Each of the 38 defects catalogued in the April 5 and April 9 audits was
re-verified against current v4.13 code. **Result: 38/38 still fixed. Zero
regressions** from the v4.12 and v4.13 releases. Evidence collected for each
defect (file + line references); full report archived in the session log.

### Fixed — Version Surface Drift

Four version surfaces had silently fallen behind since v4.9 and were never
bumped during v4.10 → v4.13 ships:

- `cli/source/package.json` (was v4.9.2026.16)
- `daemon/package.json` (was v4.9.2026.16)
- `docs/index.html` schema.org + footer (was v4.9.2026.16)
- `ROADMAP.md` header (was v4.9.2026.16)

All eight version surfaces now track together.

### Quality

- 2081 tests passing, 4 skipped (identical to v4.13 baseline).
- `ruff check clawed/ tests/`: clean.
- `mypy --strict clawed/`: 0 errors in 270 source files.
- 144 files touched by the typing pass; no behavioral changes — only
  annotations, narrow ignores, and the real-bug fixes documented above.

## v4.13.2026.1 — 2026-04-13

### Added — Competitive Borrowing (DeepTutor, Karpathy Skills, Multica)
- **Behavioral contract** in system prompt — 5 rules: verify before generating, minimal first, match teacher voice, one deliverable at a time, quality before quantity
- **Goal-driven generation** — Ed defines learning objectives (what students should DO, how to ASSESS, PREREQUISITES) before generating any lesson
- **Query diversification** in curriculum KB search — 3 query variants (original, keyword-extracted, education-context-expanded) with deduplication
- **Template compounding** — highly-rated lessons (4-5 stars) auto-saved as proven templates in `~/.eduagent/templates/`; referenced in future generation prompts

## v4.13.2026.0 — 2026-04-13

### Hardened
- Full HEARTBEAT compliance: Tier 1 decomposition (14 functions >200 lines), exception audit sweep (130 narrowed, 55 logged)
- HEARTBEAT CI workflow (function size + exception swallow checks)
- Per-module coverage enforcement planned

### Quality
- 2081 tests passing, ruff clean with expanded rules (UP/B/SIM/RUF)
- Zero bare `except Exception: pass` in codebase
- All audit findings from 3 external reviews resolved

## v4.12.2026.2 — 2026-04-12

### Hardened
- Expanded ruff rule set to include UP, B, SIM, RUF categories; 528 auto-fixed violations
- Added branch coverage tracking and coverage artifact upload to CI pipeline
- Documented all broad exception handlers in `export_pptx.py` and `ingestor.py`; narrowed where possible
- Resolved last remaining TODO in `agent_core/loop.py` (export guarantee nudge)
- Converted diagnostic `print()` calls to structured logging in `bridge.py` and `evaluation.py`

## v4.9.2026.14 (2026-04-09)

### Triple Audit Remediation — Integration Completeness

**Approval system completed:**
- `get_standing_approval()` implemented in ApprovalManager — positive approval path now works end-to-end
- Registration warns on missing risk_level (not blocking, but visible)
- All 48 tools annotated with explicit risk_level (read_only, write_local, network_call, package_install)
- Core teacher tools (generate_lesson, etc.) classified as read_only — no approval deadlock
- request_approval classified as read_only — no circular dependency

**Chrome extension auth fixed:**
- Bearer token sent on all fetch calls from background.js
- Popup has token config UI with save/connect flow
- Clear 401 error messages distinguish auth failure from network failure

**Classroom auth split:**
- Teacher routes (start, next-slide, timer, poll): require Bearer token
- Student routes (state, respond, websocket): on separate student_router, class code is auth
- WebSocket validates code BEFORE accept() — rejects with 1008 on invalid code

**Legacy ?token= removed:**
- URL token middleware completely removed from server.py
- Only POST /api/auth/bootstrap and Bearer header remain
- Auth denied page shows POST form, not URL instructions

**CORS fixed:**
- `chrome-extension://*` replaced with `allow_origin_regex=r"^chrome-extension://[a-z]{32}$"`

**Documentation:**
- docs/TOOL_POLICY.md — risk classification guide for contributors

## v4.9.2026.13 (2026-04-09)

### Fresh Audit Remediation — Unauthenticated Surfaces Closed
**P0-1: Extension/classroom/community routes now require auth.** `Depends(require_auth)` added to the entire extension router. Chrome extension must send Bearer token.
**P0-2: Onboarding mutation routes now require auth.** `persona-form`, `step`, and `state` endpoints gated.
**P0-5: WriteFileTool restricted.** Denylist blocks writes to config.json, secrets.json, api_token, schedule.json, bot_state.db, approvals.db, state.db, drive_token.json. Protected directories: memory/, corpus/, cache/. Default writes go to workspace/ subdirectory. SelfModifyConfigTool and WriteFileTool declare risk_level=write_local.
**P2-12: Docker runs as non-root.** Created `clawed` user/group, set ownership on /data, switched with USER directive.

## v4.9.2026.12 (2026-04-09)

### PERFECT Release — All Audit Defects Resolved
**F6 COMPLETE: All 23 hardcoded paths migrated to paths.py**
- models.py, student_telegram_bot.py, transports/student_telegram.py, asset_registry.py, slide_images.py, bot_state.py, tools.py (5 instances), agent_core/tools/ingest_materials.py (2), agent_core/tools/generate_animation.py, agent_core/tools/read_heartbeat.py, agent_core/tools/read_workspace.py, agent_core/memory/episodes.py, agent_core/approvals.py, agent_core/autonomy.py, agent_core/core.py, agent_core/drive/auth.py, memory_engine.py, sub_packet.py, search.py, commands/generate_ingest.py, commands/generate_standards.py (2), skills/library.py, handlers/ingest.py (2), handlers/export.py, oauth_refresh.py, state.py, transports/telegram.py (2)
- Zero remaining hardcoded paths without EDUAGENT_DATA_DIR check

**F11: Job status tracking added to scheduler**
- _job_status dict tracks: status (running/completed/failed), last_run, result, error
- GET /api/scheduler/status exposes all job state

**Low-severity polish:**
- L1: Hex validation in compile_project._hex_rgb() — fallback to warm brown on malformed hex
- L2: context_sentence=None handling in flashcard export
- L3: z-index lowered to 100000 (already shipped in .10)
- L4: Mobile responsive CSS for extension panel (@media max-width: 480px)
- L5: API URL configurable via chrome.storage in extension
- L7: Bloom's level numbering clarified in teaching_constitution.txt

**Final audit status: 38/38 defects resolved. Zero remaining.**

## v4.9.2026.11 (2026-04-09)

### Test Coverage & Hardening
- **25 new tests** for previously untested modules: compile_project (3), compile_audio (4), adaptive (5), classroom_profile (4), audit verification (9)
- **F8 partial**: Silent failure in generation.py config loading replaced with debug logging
- Fixed async event loop test isolation (pytest.mark.asyncio instead of manual loop)
- 1,975 tests total (was 1,950 at start of audit remediation)

## v4.9.2026.10 (2026-04-09)

### Audit Remediation Part 2 — Hardening & Test Coverage
- [F9] **Upload size limits** — per-file 100MB, per-request 500MB, max 200 files. Streamed to disk in 1MB chunks instead of reading all into memory.
- [F10] **9 new audit verification tests** — approval policy enforcement (read_only/write_local/package_install), InstallPackageTool allowlist, UDL vocab simplification ("Dr. King" fix), Common Cartridge export with namespace, send_notification graceful failure
- **z-index lowered** in extension panel (2147483647 → 100000)
- 1,959 tests total (was 1,950)

## v4.9.2026.9 (2026-04-09)

### Dual Audit Remediation — Security & Trust Boundary Hardening

**Addressing all findings from Jon's security audit (F1-F11) + Claude's code audit (27 defects).**

**Security (F1-F5):**
- [F1] **Central approval/policy layer** — every tool now declares a `risk_level` (read_only, write_local, network_call, package_install, external_publish). ToolRegistry.execute() enforces policy BEFORE tool execution. package_install and external_publish ALWAYS require teacher confirmation. The LLM cannot bypass this.
- [F2] **InstallPackageTool hardened** — curated allowlist of 15 safe packages only. Approval always required. Audit log written on install. Packages not on the list are blocked.
- [F3] **Permission bypass inverted** — CLI now defaults to permissions ENFORCED. Teacher must explicitly set `CLAWED_AUTO_APPROVE=1` to opt in. Warning printed when bypass is active.
- [F4] **Web auth refactored** — `?token=` query params no longer accepted for page auth. New `POST /api/auth/bootstrap` endpoint accepts token via POST body, sets HttpOnly/SameSite/Secure cookie, redirects to clean URL. Legacy `?token=` auto-redirects to clean URL with cookie.
- [F5] **CORS consolidated** — single middleware instance with localhost + Chrome extension origins. Duplicate removed.

**Blockers Fixed:**
- [B1] `send_notification()` created in telegram.py — scheduler can now notify teachers via Telegram
- [B2] Extension icon placeholders created (16x16, 48x48, 128x128 PNG)
- [B4] Common Cartridge XML namespace declarations added

**Code Correctness:**
- [H1] XSS fixed in content.js — all `innerHTML` replaced with `textContent` + DOM creation
- [H2] In-memory state bounded: MAX_SESSIONS=100, MAX_SOURCES=500, MAX_COMMUNITY_LESSONS=1000
- [H3] Session tokens strengthened: 6→12 char hex codes
- [H4] UDL vocab simplification fixed: `split(". ")` instead of `split(".")` — "Dr. King" no longer becomes "Dr."
- [H6] Kahoot duplicate answers fixed: plausible generic wrong answers instead of repeated "None of the above"
- [M1] WebSocket disconnect safety: KeyError guard for invalid codes
- [M2] Community rating: proper cumulative average algorithm
- [M5] Audio narration: None field handling for topic/subject/grade/homework
- [M7] KG connections: teacher_id passed from identity system instead of hardcoded empty string
- [M8] Classroom profile: technology defaults to False (teacher opts in, not out)

## v4.9.2026.8 (2026-04-09)

### The Final Four — Complete Platform
**Chrome Extension:**
- Full Manifest V3 extension with context menu ("Generate Lesson from Selection" + "Use as Primary Source")
- Content script displays results in floating panel with Claw-ED branding
- Popup with server status check and usage instructions
- API routes: `/api/extension/generate`, `/api/extension/add-source`, `/api/extension/sources`

**Real-Time Classroom Mode (Nearpod-style):**
- WebSocket-based live classroom sessions with class code
- Teacher controls: next/prev slide, start timer, launch poll
- Student endpoint: submit poll responses, view current slide state
- Routes: `/api/classroom/start`, `/api/classroom/{code}/ws`, slide/timer/poll controls

**Teacher Community & Sharing:**
- `POST /api/community/share` — anonymized lesson sharing (strips teacher identity)
- `GET /api/community/browse` — browse by subject, grade, keyword search
- `POST /api/community/{id}/rate` — community ratings
- In-memory store (ready for SQLite upgrade)

**Visible Agent Pipeline:**
- `GET /api/pipeline/status` — shows all 9 pipeline stages (Standards → Persona → Classroom → KG → LLM → Quality Gate → Critic → Vision → Compilation)
- `GET /api/pipeline/quality-report` — exposes quality gate check results
- Teachers can see exactly how Ed built their lesson

## v4.9.2026.7 (2026-04-09)

### Knowledge & Context Intelligence
- **KG-powered lesson connections** — `lesson_connections.py` queries 227K-entity knowledge graph to suggest cross-unit links, prerequisite checks, and "Previously on..." Do Now hooks. Auto-injected into every lesson generation prompt.
- **Classroom Memory** — `classroom_profile.py` with persistent `ClassroomProfile` model (student count, tech available, ELL/IEP counts, seating, LMS, textbook). Saved as JSON, auto-loaded into every generation prompt.
- **Adaptive feedback loop** — `adaptive.py` analyzes exit ticket grading results, generates adjustment context for next lesson (reteach/partial/proceed), and drafts parent notifications

### Pipeline Integration
- Classroom profile context injected into `generate_master_content()` system prompt
- KG connections injected into lesson generation prompt
- Year planner confirmed already fully wired (`clawed year-map` CLI command + CurriculumMapper)
- Sub packet confirmed already fully wired (`clawed sub-packet` CLI + agent tool)

## v4.9.2026.6 (2026-04-09)

### Everything Release — Complete Teacher Operating System
**Scheduler wired live:**
- `morning-prep` auto-generates missing lessons each morning from current unit
- `weekly-plan` drafts up to 5 lessons for next week every Sunday, notifies via Telegram
- Both handlers call real `generate_lesson()` pipeline with quality gate + persona

**Audio lesson generation:**
- `compile_audio.py` — TTS-ready narration scripts from teacher_script fields
- `compile_audio_mp3()` — direct MP3 export via OpenAI TTS API (optional)
- Structured for natural reading: hooks, pauses, vocabulary previews, key points

**Multi-agent critic pipeline:**
- Teaching Constitution now wired into generate_master_content() as Stage 2 critic
- Separate LLM call reviews every lesson against 8 pedagogical principles
- Non-blocking — if critic fails, lesson still ships with warnings

**LMS export formats:**
- **Common Cartridge (.imscc)** — ZIP+XML package that imports directly into Canvas, Moodle, Blackboard, Schoology. No API keys needed.
- **Google Classroom** — `post_to_google_classroom()` creates coursework via Classroom API using existing OAuth credentials
- **UDL 3-tier generation** — `generate_udl_tiers()` mechanically creates on-level, scaffolded (word banks, sentence starters, simplified vocab), and enriched (extension tasks, modern parallels) versions

**Exit ticket auto-grading:**
- `grade_exit_ticket()` scores student responses against MasterContent answer keys
- Keyword overlap + length analysis for instant scoring (0-4 scale)
- Formative feedback with sentence starters when score < 4
- Returns score, feedback, meets_standard, cognitive_level

## v4.9.2026.5 (2026-04-09)

### The Autonomous Teaching Partner Release
- **Bloom's Enforcer** — quality gate now requires cognitive progression (recall → application → analysis) in exit tickets. Research showed 98% of AI lessons stuck at memorization. Not anymore.
- **Voice enforcement** — quality gate requires `lesson_personality` and `hook` on first DI section. No more "today we will learn about..." openings.
- **Diversity & Inclusion audit** — quality gate scans for exclusionary language (primitive, uncivilized, etc.) and flags for revision
- **Jigsaw enforcement** — if lesson_format is "jigsaw", structured jigsaw field is required
- **AI-Resistant Assignments** — prompt now requires independent_work that ChatGPT can't fake (personal interviews, local observations, live performances, physical creations)
- **Teaching Constitution** — `teaching_constitution.txt` critic prompt for future reflection pipeline (8 pedagogical principles from Danielson + Bloom's + UDL)
- **Scheduler activated** — morning-prep, weekly-plan, gap-detection, curriculum-watch, and self-distill now ENABLED by default. Ed is autonomous.
- **Anki flashcard export** — `compile_flashcards.py` generates TSV from vocabulary + guided notes + key points. Import directly into Anki for spaced repetition.
- **Kahoot quiz export** — CSV with vocabulary MC questions + exit ticket review items. Direct import into Kahoot.
- **Study guide export** — plain-text review sheet combining all lesson content
- 18 new tests (1950 total), all passing

## v4.9.2026.4 (2026-04-09)

### Multi-Day Project Arcs
- **ProjectArc, ProjectPhase, CulminatingPerformance** models — complete project data structures
- **project_arc.txt** prompt — generates 5-day project arcs modeled on Jon's "Voices of Change" packet
- **generate_project_arc()** in lesson.py — LLM generates project with phases, choice boards, rubric, debate prep
- **compile_project.py** — compiles ProjectArc into student-facing DOCX with day-by-day roadmap, topic/format choice boards, graphic organizer table, curated research database links, debate prep sheet, 4-point rubric, and culminating performance instructions
- **UnitPlan.project** field — units can now include a project arc for multi-week sequences

## v4.9.2026.3 (2026-04-09)

### The Voice & Structure Revolution
- **Lesson personality** — every lesson gets a one-line theme/hook ("Today we're putting Hammurabi on trial")
- **Hooks & transitions** — first DI section requires an opening hook; all sections require scripted transitions
- **Sentence starters & writing frameworks** — TEA/RACE/CER scaffolds on every exit ticket question
- **Minute-by-minute pacing** — full timing chart for every lesson
- **Structured jigsaws** — JigsawStructure model with expert/teaching group rotation, timed phases, graphic organizer, share-out protocol, debrief question
- **Creative activities** — CreativeActivity model for role plays, debates, podcasts, social media campaigns, gallery walks, mock trials, time travel scenarios
- **Station enhancements** — timer_minutes, group_roles, reporting_template fields
- **DOCX compilation** — jigsaw graphic organizer rendered as real table, creative activity sections with deliverable templates, sentence starters on exit tickets
- Prompt expanded with Voice & Personality, Jigsaw, Creative Activity, and Minute-by-Minute sections (~100 new lines)

## v4.9.2026.2 (2026-04-09)

### Vision-Powered Image Quality Filter
- **Vision model quality gate** — every fetched image is evaluated by a vision-capable LLM before embedding
- Images scored on relevance, clarity, and classroom appropriateness (GOOD/ACCEPTABLE/REJECT)
- Rejected images are logged and excluded from lesson output
- Permissive fallback — if no vision model is configured, all images pass (never blocks)
- Supports Anthropic (Claude) and OpenAI (GPT-4) vision APIs
- New `generate_with_image()` method on LLMClient for multimodal prompts

## v4.9.2026.1 (2026-04-09)

### Output Quality Revolution
- **Quality gate with auto-retry** — validates 8 rules (primary source length, image specificity, exit ticket stimuli, guided notes minimum, teacher script CFU, differentiation ban list, self-contained check, station answer keys); retries 2x with specific failure feedback injected into the prompt
- **Few-shot quality exemplars** in master_content.txt — full worked examples of good/bad primary sources, CRQ exit tickets, and differentiation so the LLM sees the standard
- **Lesson context chaining** — `generate_all_lessons()` passes cumulative vocabulary, sources, and objectives between lessons so Day 3 builds on Day 2

### Visual Overhaul
- **Warm brown color palette** (#8B6914/#F5E6C8/#2C1810) for History and Social Studies
- **Subject-aware theming** across DOCX and PPTX — each subject gets its own professional palette
- **IEP/ELL/Gifted differentiation callout boxes** — gold, teal, and green visual treatment
- **Page breaks** between major DOCX sections (primary sources, exit ticket, differentiation)
- **Themed table headers** — white text on subject-colored backgrounds

### Architecture
- **PPTX subpackage** (`clawed/pptx/`) — helpers, themes, and images extracted from the 1600-line monolith
- **Granular exception handling** in generation.py — ConnectionError, TimeoutError, ValueError caught separately with full logging
- **MasterContent validators** for content_text length and image_spec specificity
- **humanize.py** — added "in conclusion" and "to conclude" to Tier 1 ban list
- 34 new tests (1932+ total)

## v4.8.2026 (2026-04-08)

### Major release — human voice, image dedup, curriculum visualizer

Four pillars shipping together:

### 1. AI writing removal (avoid-ai-writing)
- **humanize.py**: 70+ Tier 1 word replacements (delve→explore, utilize→use,
  leverage→use, etc.), Tier 2 cluster detection, Tier 3 density detection
- **Prompt-level ban list**: Ed's system prompt now explicitly bans 30+ AI-isms
  so the LLM avoids them from the start
- **Post-generation filter**: `humanize()` runs on all MasterContent text
  (direct instruction, vocabulary, exit ticket) before DOCX/PPTX compilation
- Source: https://github.com/conorbronsdon/avoid-ai-writing

### 2. Image dedup — no more repeated images
- **`_resolve_from_teacher_assets()`**: now requests 10 candidates per spec
  and tracks used paths — each slide gets a unique image
- **`export_pptx.py`**: same dedup logic for the legacy PPTX export path
- Root cause: `limit=1` returned the same top-scoring image for every spec

### 3. Curriculum visualizer (Graphify-inspired)
- **`curriculum_visualizer` tool**: generates interactive HTML page from
  the knowledge graph using vis.js — teacher sees their entire curriculum
  as a connected visual map with color-coded node types
- Click nodes to see relationships, scroll to zoom, drag to pan
- Source: https://github.com/safishamsi/graphify

### 4. Full unified ingestion pipeline
- All of v4.7's work consolidated: `full_ingest()` handles parse → images
  → assets → chunks → KG → wiki in one call
- 58,310 teacher images now flow into generated PPTX slides
- Wiki compilation with async fix (GLM 5.1 / any LLM)

### Stats
- 1821 tests pass, ruff clean, zero version drift
- 3 new modules: humanize.py, curriculum_visualizer.py
- 48+ tools total

## v4.7.2026.11 (2026-04-07)

### Fix async wiki compilation in full_ingest()

`compile_wiki()` is async but was called synchronously, returning a
coroutine object instead of the result. Fixed with proper `asyncio.run()`
handling that works in both sync and async contexts.

## v4.7.2026.10 (2026-04-07)

### Unified ingestion pipeline — images finally flow

Root cause found: standalone ingestion never called `extract_rich()` or
`register_asset()`. Images existed in the PPTX files but were never
extracted to the asset registry. Created `full_ingest()` — ONE function
that does the complete pipeline: parse → extract images → register assets
→ index chunks → build KG → compile wiki. Wired into both CLI `clawed
ingest` and the agent `ingest_materials` tool.

- **`full_ingest()`** in `clawed/ingestor.py` — single entry point for all ingestion
- **CLI refactored** — `clawed ingest` now uses `full_ingest()` instead of
  4 separate blocks
- **Agent tool refactored** — `ingest_materials` uses `full_ingest()` instead
  of assembling the pipeline manually
- No entry point can miss images again — they all go through the same function

## v4.7.2026.9 (2026-04-07)

### Bug fixes: game tool + animation tool

- **generate_game**: fixed `compile_game() got unexpected keyword argument game_type` — param is `game_style`
- **generate_animation**: fixed `ToolResult.__init__() got unexpected keyword argument failure_code` — use `data` dict

## v4.7.2026.8 (2026-04-07)

### Clean branded startup — teacher name, no Anthropic references

- Banner shows teacher name + model instead of OAuth account info
- Removed "Running in Python mode" developer message
- Suppressed Anthropic OAuth org name from status line in Claw-ED mode
- Suppressed guest pass and referral upsells in Claw-ED mode
- EmergencyTip already suppressed (line 9 guard)
- Project onboarding tips already suppressed (CLAWED_MODE guard)

## v4.7.2026.7 (2026-04-07)

### Auto wiki compilation during ingestion

Wiki articles are now automatically compiled from indexed chunks at
the end of the ingestion pipeline. The teacher no longer needs to
manually run `clawed kb compile` — Ed does it automatically. Full
pipeline: parse → sanitize → chunk → embed → images → assets → KG → wiki.

## v4.7.2026.6 (2026-04-07)

Sanitizer fix included in PyPI (see .5 notes).

## v4.7.2026.5 (2026-04-07)

### MCP server expansion + bulletproof text sanitizer

**Sanitizer v2**: requires >40% letters + at least 2 real words per line.
Kills URL-encoded garbage (`%3D%26`), OLE/OOXML internals (`bjbj`,
`timingInfo.xml`), binary-as-text, while keeping all real educational
content including standard codes and vocabulary lists.

### MCP server — 11 tools (was 5)

Added 6 new MCP tools for Claude Code / Hermes Agent integration:

- **search_curriculum**: semantic search over teacher's ingested materials
  (KB chunks with similarity scores, source paths, full text)
- **query_knowledge_graph**: topic relationships — prerequisites, related
  topics, standards, vocabulary from the curriculum KG
- **kg_stats**: knowledge graph statistics (entities, triples, types)
- **search_session_history**: semantic search over compressed past sessions
- **query_wiki**: Q&A over the compiled Karpathy-style curriculum wiki
- Updated server instructions to highlight search-first workflow

Compatible with Claude Code 2.1.91+ maxResultSizeChars annotation
for large curriculum search results (up to 500K chars).

## v4.7.2026.4 (2026-04-07)

### Smart chunking + text sanitization (replaces hard cap)

- **Removed per-document chunk cap** — large docs are handled properly now
- **Slide-aware chunking**: PPTX text with `[Slide N]` markers is chunked
  per slide (1 chunk per slide) instead of 500-word overlapping windows.
  A 500-slide deck = 500 chunks, not 300K
- **Text sanitization before chunking**: strips base64 blobs, XML/HTML tags,
  binary artifacts, and lines that are mostly non-alphanumeric. This is
  why "1960s America 2023" generated 311K chunks — the parser was extracting
  embedded garbage as text
- No document is ever truncated or skipped — sanitize and chunk correctly

## v4.7.2026.3 (2026-04-07)

### Per-document chunk cap — prevents runaway indexing

- **_MAX_CHUNKS_PER_DOC = 2000**: corrupted PPTX files were generating
  up to 311K chunks per document (e.g., "1960s America 2023"). A 500-slide
  deck with 500 words/slide = ~500 chunks — 2000 is generous. Files
  exceeding the cap are logged and truncated, not skipped.
- **glm-5.1:cloud** added to Ollama catalog

## v4.7.2026.2 (2026-04-07)

### Memory-safe ingestion for any document size

- **Batch indexing**: CurriculumKB.index() now processes chunks in batches of
  50 with gc.collect() between batches — a 10,000-chunk document uses the same
  memory as a 10-chunk one. Fixes OOM on large PPTX files (e.g., 9,429 chunks)
- **OpenRouter GLM 5.1 support**: added to model discovery catalog

## v4.7.2026.1 (2026-04-07)

### Curriculum knowledge graph + session compression

Inspired by MemPalace (11K-star AI memory system). Two new memory layers.

### Knowledge graph
- **CurriculumKG**: temporal triple store for curriculum concepts — topics,
  standards, skills, figures, vocabulary with prerequisite/builds_on/related_to
  relationships and temporal validity windows
- **Entity extraction**: heuristic extraction from doc titles, content,
  tags, and standard codes during ingestion (no LLM, fast)
- **Prompt injection**: `get_topic_context()` feeds prerequisites, related
  topics, standards, and vocabulary into lesson generation prompts
- **Semantic entity search**: ONNX MiniLM embeddings on entity names for
  fuzzy topic matching
- **Batch embedding**: `batch_embed_unembedded()` for fast post-ingest pass

### Session compression
- **Structured summaries**: compresses oldest 20 turns into topics, materials
  generated, decisions, feedback with 2-3 sentence heuristic summary
- **Semantic recall**: compressed summaries embedded for future search
- **Auto-trigger**: `maybe_compress_sessions()` fires after each interaction
  when turn count exceeds 40; keeps last 20 verbatim
- **Timeline merge**: `get_full_session_timeline()` merges recent turns +
  compressed summaries chronologically

### Integration
- Ingestion pipeline: KG populated during `ingest_materials` tool with
  entity extraction + relationship inference
- Context loader: Layer 6b (session history) + Layer 7 (KG context)
- Lesson generation: KG topic context injected alongside KB search results
- Agent loop: session compression trigger after `maybe_compress_episodes`

### Stats
- 3 new modules, 2 new test files, 48 new tests
- 1821 total tests, 0 failures, ruff clean

## v4.7.2026 (2026-04-07)

### Teacher image pipeline + animated educational videos

The #1 user complaint was that generated lessons used generic stock photos
instead of the teacher's own maps, cartoons, and diagrams — even though
31,165 images had been extracted from 2,495 PPTX files. Fixed.

### Image pipeline
- **Critical fix**: generate_lesson_bundle.py now passes teacher_id to
  fetch_all_images() — this single missing parameter was why zero teacher
  images appeared in generated lessons
- **export_pptx.py**: added teacher-asset Phase 1 lookup before Wikimedia
  fetch — the legacy PPTX export path now also checks teacher's own images
- **Semantic image matching**: when keyword search returns 0 results,
  falls back to ONNX MiniLM embedding similarity between image_spec and
  teacher asset context_text
- **Topic-tag enrichment**: _extract_topic_tags() now parses curriculum
  directory structure (e.g., "7th us history 1/22-23/") for richer metadata
- **teacher_id threaded** through all 3 export paths: generate_lesson_bundle,
  export_document tool, and handlers/export.py

### Animated educational videos (Manim)
- **New tool: generate_animation** — creates 3Blue1Brown-style animated
  educational videos (MP4) via Manim Community Edition
- **6 animation templates**: HistoricalTimeline, CauseEffectDiagram,
  ProcessFlow, ConceptMap, VennComparison, VocabularyCard
- **5-stage pipeline**: PLAN → CODE → RENDER → VALIDATE → DELIVER
- **Education-optimized**: max 6 on-screen elements, 2-3s pauses between
  reveals, sans-serif fonts for projector readability
- **Optional dependency**: `pip install clawed[animations]` — graceful
  degradation when manim not installed
- Adapted from Hermes agent manim-video skill architecture

### Hygiene
- Zero version drift: all 16 version surfaces aligned at 4.7.2026
- New failure codes: MISSING_DEPENDENCY, RENDER_FAILED
- Landing page updated with image and animation features
- 1773 tests pass, 0 failures

## v4.6.2026 (2026-04-06)

### Major release — model system, security hardening, agent autonomy

This release consolidates 36 incremental pushes from the v4.5 series
into a clean milestone. Every audit finding addressed, all version
surfaces aligned, CI green across Python, Docker, and TypeScript.

### Model system
- Default model: gemma4:31b-cloud (100% tool-call success, proven in 3-lesson test)
- Interactive /models command on Telegram (inline keyboard: provider → model)
- Model discovery module: dynamic Ollama Cloud + OpenRouter API listing
- Full Ollama Cloud catalog: 24 models with tool-use tags
- OpenRouter free model catalog: 6 curated free models
- OpenRouter tool-use routing fixed (was going to Ollama path, now native)
- OpenRouter timeout increased to 300s for free tier models
- Codex OAuth evaluated and removed (doesn't work for API calls)

### Security + hygiene
- Page auth cookie: ?token= now sets httponly cookie for 24h session
- Onboarding recommends Ollama Pro, mentions /models command
- lru-cache pinned to 10.4.3 (fixes CI TypeScript build)

## v4.5.2026.29 (2026-04-05)

### Hygiene
- Version drift eliminated: CHANGELOG, ROADMAP, pyproject.toml, PyPI all aligned
- Security tests run without localhost bypass — real 401/429 assertions
- Self-equipping gated: install_package requires teacher confirmation, README documents trust model
- README self-equipping claim scoped and explained
- Docker CI fixed (empty CLI bundle stub for hatchling)

## v4.5.2026.28 (2026-04-05)

### Global state + security tests
- Centralized path provider (clawed/paths.py)
- 18 security regression tests (auth, rate limit, SSRF)
- Exception handling narrowed in 4 startup blocks
- Architecture doc keyring name corrected
- Docker CI smoke test added

## v4.5.2026.27 (2026-04-05)

### Security hardening (audit remediation)
- Auth on ALL API routes (ingest, export, feedback, lessons, school)
- Auth on ALL HTML pages (dashboard, settings, analytics, profile, etc.)
- Health endpoint split: `/api/health` (liveness) + `/api/health/diagnostics` (auth-protected)
- Import URL lockdown: SSRF protection, localhost-only by default
- Public share pages (`/share/{token}`, `/student/{code}`) remain intentionally open

### v4.5.2026.26 (2026-04-05)
- Real rate limiting (in-memory, per-IP per-route)
- Bearer token auth for web API
- CORS restricted to localhost
- Docker defaults to 127.0.0.1
- Docker extra fixed (`.[hosted]` -> `.[all]`)
- Local QR generation (removed third-party api.qrserver.com)
- Skip-permissions now configurable via `auto_approve_tools`
- Non-localhost warning on `clawed serve`

### v4.5.2026.25 (2026-04-05)
- Multi-provider tier routing: `tier_providers: {"fast": "ollama", "deep": "anthropic"}`
- Enhanced switch_model tool: switch_provider, set_tier, list_providers

### v4.5.2026.20 (2026-04-05)
- Telegram transport switched from httpx to requests (Windows TLS fix)
- Ed never asks teacher to run commands (agentic prompt)
- Landing page rewrite (611 lines, open source tone)
- README rewrite (features list, no marketing)

### v4.5.2026 (2026-04-04)
- Agentic identity rewrite: autonomous master educator
- Teacher image integration in image pipeline
- New tools: generate_game, generate_simulation, differentiate_lesson
- Self-modification tools: modify_config, write_file, read_file
- CJK sanitizer for minimax model

### v4.4.2026 — v4.4.2026.6 (2026-04-04)
- v5 Magnum Opus: 7 phases shipped
  - Phase 1: Cross-transport sessions (CLI + Telegram share memory)
  - Phase 2: Google Drive OAuth + CLI commands + ingest tool
  - Phase 3: Browser tools (web search, navigate, research)
  - Phase 4: Quality tracker + pattern detection
  - Phase 5: Proactive Ed (gap detection, curriculum watch)
  - Phase 6: Self-equipping (pip install, custom YAML tools)
  - Phase 7: File management + workspace status
- ONNX MiniLM embedder (384-dim, binary BLOB storage)
- FTS5 two-stage search
- Karpathy wiki (compile, query, lint)
- Self-distillation (learns from ratings and edits)

### v4.3.2026.21 (2026-04-04)
- Unified teacher identity across transports
- Drive tool definitions registered
- Ed personality rewrite in prompt.py
- Think block stripping for reasoning models

### v4.3.2026.13 (2026-04-02)
- Architecture docs rewritten
- Model guide updated
- Bot setup guide updated
- Contributing guide updated

### Earlier versions
See git history for v1.x through v4.3.x releases.
