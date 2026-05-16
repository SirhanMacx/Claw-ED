# Claw-ED Architecture

## Overview

Claw-ED is a persistent AI teaching assistant. Ed lives in your terminal and on your phone, generating lessons, assessments, and materials in your teaching voice.

This document describes the v5.15.2026 architecture -- how messages flow through the system, what each module does, and how components connect.

---

## System Diagram

```
Teacher
  |
  +-- Terminal: clawed --> Entry Router (_entry_router.py)
  |                          +-- First-run? --> Python onboarding wizard
  |                          +-- Subcommand? --> Python CLI (typer)
  |                          +-- Interactive? --> Node.js Ink TUI
  |                                                +-- Anthropic API (direct)
  |                                                +-- Bridge --> Python LLM Client
  |                                                                +-- OpenAI
  |                                                                +-- Google Gemini
  |                                                                +-- Ollama (cloud/local)
  |                                                                +-- OpenRouter
  |
  +-- Phone: Telegram bot (auto-started as background daemon)
                +-- Python Gateway --> Agent Loop --> Tools
```

---

## Entry Router (`clawed/_entry_router.py`)

The entry router is the single `clawed` command entry point. It handles six responsibilities before any teaching work begins:

1. **First-run detection.** If `~/.eduagent/config.json` does not exist, the router launches the Python onboarding wizard (`clawed.onboarding.quick_model_setup`) before anything else. The wizard walks the teacher through provider selection, API key entry, and mode choice (terminal vs. Telegram).

2. **Provider env injection.** `_inject_config_env()` reads the teacher's saved config and sets the appropriate environment variable (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_API_KEY`, `OPENROUTER_API_KEY`) so the Node.js TUI can authenticate without its own config layer.

3. **API key resolution (5-step chain).** `_resolve_key_for_provider()` searches for credentials in order: environment variable, Claude Code OAuth credentials (`~/.claude/.credentials.json`), OS keyring (`keyring` library), `~/.eduagent/secrets.json`, and finally inline config fields. The first match wins.

4. **Auto-daemon for Telegram.** `_maybe_start_bot_background()` checks whether a Telegram bot token is configured. If so and no bot is already running (checked via `bot.lock` PID), it spawns `python -m clawed bot` as a detached background process. The teacher never needs to start the bot manually.

5. **Model injection.** `_get_configured_model()` reads the teacher's chosen model from config and injects `--model` into the Node CLI args so it uses the right model instead of defaulting.

6. **Node TUI launch (permission bypass opt-in).** For interactive mode, the router launches `node cli.js`. Permission bypass is **disabled by default** (hardened in the F3 security audit). Teachers who want to skip developer-facing trust prompts must explicitly opt in via `CLAWED_AUTO_APPROVE=1` environment variable or `auto_approve_tools: true` in `config.json`. When active, `--dangerously-skip-permissions` is injected into the Node args, but only `read_only` tools skip confirmation -- sensitive operations still go through the central approval policy layer. Python subcommands (a set of ~50 known command names) are routed directly to the Python typer CLI instead.

---

## Agent Core (`clawed/agent_core/`)

The agent core is the LLM-driven brain that powers both Telegram and direct Python interactions.

```
clawed/agent_core/
+-- core.py           # Gateway.handle() entry point
+-- loop.py           # _agent_loop(): tool-use loop (max 20 iterations)
+-- prompt.py         # System prompt assembly from persona + workspace + tools
+-- context.py        # Workspace context loading (soul, memory, curriculum)
+-- tools/            # 43 auto-discovered tool modules (see below)
+-- approvals.py      # Approval manager for sensitive operations
+-- autonomy.py       # Autonomy level configuration
+-- planner.py        # Multi-step plan execution
+-- scheduler.py      # Background task scheduling
+-- memory/           # Conversation memory and retrieval
+-- drive/            # Google Drive integration tools
+-- custom_tools.py   # Teacher-defined custom tools
+-- fake_llm.py       # Mock LLM for testing
```

**Message flow:** `Gateway.handle(message)` is the main entry point. It first checks deterministic control-plane handlers (file ingestion, onboarding callbacks, approval flows). If none match, it enters `_agent_loop()`, which assembles a system prompt from the teacher's persona and workspace context, then runs a tool-use loop: send message to LLM, execute any tool calls, feed results back, repeat until the LLM produces a final text response or hits the iteration limit.

---

## Teaching Tools

There are 15 teaching tools exposed through the Node.js Ink TUI, each implemented as a TypeScript file in `cli/source/src/tools/clawed/`:

| Tool file | What it does |
|-----------|-------------|
| `LessonTool.ts` | Generate a daily lesson plan |
| `UnitTool.ts` | Generate a multi-week unit plan |
| `MaterialsTool.ts` | Generate worksheets, handouts, activities |
| `AssessmentTool.ts` | Generate quizzes, tests, rubrics |
| `DifferentiateTool.ts` | Generate IEP/504 accommodations |
| `ExportTool.ts` | Export to PDF, DOCX, PPTX, Markdown |
| `IngestTool.ts` | Ingest curriculum files (PDF, DOCX, PPTX, etc.) |
| `PersonaTool.ts` | Extract or update teaching persona |
| `StandardsTool.ts` | Search and align to standards |
| `SearchCurriculumTool.ts` | Search existing materials |
| `StudentsTool.ts` | Student bot and class management |
| `TrainTool.ts` | Train Ed on your teaching voice |
| `ReviewTool.ts` | Review and improve generated content |
| `GameTool.ts` | Generate interactive review games |
| `SimulationTool.ts` | Generate interactive simulations |

**Bridge pattern:** Each TS tool spawns `python3 -m clawed <command> --json` via `_bridge.ts`, passing arguments as CLI flags. The Python side executes the generation and returns structured JSON. This lets the Node TUI handle rendering while Python handles all LLM calls and content logic.

The agent core has its own set of 43 Python-native tool modules (51 tool classes) in `clawed/agent_core/tools/` used by the Telegram bot and direct Python paths. These include everything the TS tools do plus Drive integration, scheduling, workspace management, and heartbeat monitoring.

---

## Master Content Track

Claw-ED uses a single-generation, multi-compilation architecture. One LLM call produces a `MasterContent` object (`clawed/master_content.py`) containing all the raw instructional content for a lesson. Separate compilers then mechanically transform that master into different output formats -- no additional LLM calls required.

```
LLM Generation (one call)
      |
      v
  MasterContent (JSON)
      |
      +---> compile_teacher.py   --> Teacher lesson plan (full, with answer keys)
      +---> compile_student.py   --> Student packet (no answers, clean layout)
      +---> export_pptx.py       --> Slide deck (via compile_slides.py)
      +---> compile_game.py      --> Interactive review game (HTML)
      +---> compile_simulation.py --> Interactive simulation (HTML)
```

This means editing the master content automatically updates every downstream format on recompilation.

---

## Compilation Pipeline

| Module | Input | Output |
|--------|-------|--------|
| `compile_teacher.py` | MasterContent | Teacher-facing lesson plan with answer keys, timing, differentiation notes |
| `compile_student.py` | MasterContent | Student-facing packet stripped of answers and teacher notes |
| `compile_slides.py` | MasterContent | Slide structure for PPTX export |
| `export_pptx.py` | Slide structure | PowerPoint file via python-pptx |
| `compile_game.py` | MasterContent | Self-contained HTML review game |
| `compile_simulation.py` | MasterContent | Self-contained HTML interactive simulation |

Additional exporters: `export_pdf.py` (ReportLab), `export_docx.py` (python-docx), `export_markdown.py`, `export_handout.py`, `doc_export.py` (unified dispatcher).

---

## Data Storage

All persistent data lives under `$EDUAGENT_DATA_DIR` (defaults to `~/.eduagent/`):

```
~/.eduagent/
+-- config.json              # Provider, model, output dir, teacher profile
+-- secrets.json             # API keys (0600 permissions, keyring fallback)
+-- state.db                 # Teacher sessions (SQLite)
+-- task_queue.db            # Background task queue (SQLite)
+-- bot_state.db             # Telegram bot conversation state (SQLite)
+-- bot.lock                 # PID lock file for background bot daemon
+-- workspace/
|   +-- SOUL.md              # Ed's identity and teacher's voice profile
|   +-- MEMORY.md            # Persistent cross-session memory
|   +-- notes/               # Teacher's working notes
+-- memory/
|   +-- curriculum_kb.db     # Curriculum knowledge base (SQLite)
+-- wiki/                    # Compiled curriculum wiki articles
+-- corpus/
    +-- corpus.db            # Few-shot examples for prompt injection (SQLite)
```

### Filesystem Boundary Layer

Agent tools that read or write files must resolve user-supplied paths through `clawed.paths.path_is_within()` instead of string prefix checks. This prevents prefix-sibling escapes such as `/tmp/workspace-evil` being treated as inside `/tmp/workspace`.

Current protected surfaces:
- Workspace reads (`read_workspace`)
- Self-modification reads and writes (`read_file`, `write_file`)
- Output file listing and organization (`list_output_files`, `organize_files`)
- Material ingestion home-directory guard (`ingest_materials`)

API token storage also resolves `EDUAGENT_DATA_DIR` at call time through `clawed.paths.api_token_path()`, so tests, Docker runs, and multi-profile launches do not accidentally reuse an import-time token path.

---

## Multi-Provider Auth

The 5-step API key resolution chain (implemented in `_entry_router.py._resolve_key_for_provider()`):

1. **Environment variable** -- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc. If set, the teacher knows what they are doing; use it directly.
2. **Claude Code OAuth** -- For Anthropic provider only, checks `~/.claude/.credentials.json` for an OAuth access token. This lets teachers who already use Claude Code skip API key setup entirely.
3. **OS keyring** -- macOS Keychain, Linux Secret Service, or Windows Credential Manager via the `keyring` library. Stored under service name `"eduagent"` (matching `~/.eduagent/` data directory for backwards compatibility).
4. **secrets.json** -- `~/.eduagent/secrets.json`, a JSON file with `0600` permissions. Fallback when keyring is unavailable.
5. **Config inline** -- Fields like `ollama_api_key` in `config.json`. Skips sentinel values like `"ollama-local"`.

The LLM client (`clawed/llm.py`) supports Anthropic, OpenAI, Google Gemini, Ollama (cloud and local), and OpenRouter. The model router (`clawed/model_router.py`) maps task types to appropriate models -- fast models for quick Q&A, strong models for lesson generation.

---

## Curriculum Wiki (Karpathy Architecture)

The curriculum knowledge base (`clawed/wiki.py` + `clawed/commands/kb.py`) follows a retrieve-compile-query pattern inspired by Karpathy's approach to knowledge management:

```
Raw files (PDF, DOCX, PPTX, etc.)
      |
      v
  ingest --> chunks (text splitting + metadata extraction)
      |
      v
  kb compile --> SQLite full-text search index (curriculum_kb.db)
      |
      v
  markdown articles (compiled wiki/ directory)
      |
      v
  kb query --> search results injected into LLM context
```

Teachers ingest their existing curriculum materials. The system chunks them, extracts topic tags, and compiles a searchable knowledge base. When Ed generates new content, he queries this KB to ground his output in the teacher's actual curriculum rather than generic knowledge.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ (backend), TypeScript (TUI) |
| TUI | Ink (React for CLI) via Node.js |
| CLI | Typer + Rich (Python fallback) |
| Async HTTP | httpx |
| LLM APIs | anthropic, openai, google-generativeai, ollama (via HTTP) |
| Data validation | Pydantic 2.x |
| Templating | Jinja2 |
| File ingestion | pypdf (PDF, MIT-licensed base), python-docx, python-pptx. PyMuPDF available as opt-in `pdf-rich` extra (AGPL). |
| Slide export | python-pptx |
| PDF export | ReportLab |
| Database | SQLite (WAL mode) |
| Bot | python-telegram-bot (polling mode) |
| Linting | Ruff |
| Testing | pytest + pytest-asyncio |

---

## Trust Model — Single-Operator Architecture (ED-4)

Claw-ED is designed as a **single-teacher-per-instance** application. The `get_default_teacher()` function returns the most recently created teacher record and all API routes implicitly operate on that teacher's data. There is no per-request tenant isolation.

**Current guarantees:**
- One teacher persona governs all generation and chat.
- Bearer token auth protects teacher-only routes; students access only their designated endpoints (class code, share token).
- In-memory stores (classroom sessions, saved sources, community lessons) are process-global.

**What this means:**
- Running a single Claw-ED instance for multiple independent teachers would leak data across teachers.
- Each teacher should run their own instance (separate process, separate database).

**Upgrade path (v5.0):**
1. Add `teacher_id` to every API request via a per-request auth middleware.
2. Scope all DB queries and in-memory stores by `teacher_id`.
3. Replace `get_default_teacher()` with `get_teacher_for_request(request)`.
4. Migrate in-memory stores to a persistent, tenant-scoped backend (Redis or SQLite).
