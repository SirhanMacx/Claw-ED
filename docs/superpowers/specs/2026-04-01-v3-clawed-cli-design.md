# Claw-ED v3.0 Design Spec

> Historical design, superseded in v9.18.2026.1. The bundled terminal and daemon were retired. See [the current architecture](../../ARCHITECTURE.md).

**Date:** 2026-04-01
**Status:** Reviewed (rev 2)
**Author:** Claude (with Jon)

## Vision

Claw-ED v3.0 absorbs the Claude Code source build as its terminal interface. Teachers get a persistent AI co-teacher in a beautiful Ink/React TUI, branded as Claw-ED with an animated professional ASCII logo, educational color palette, and all 16 lesson generation features accessible through natural language or direct commands. A background daemon keeps the Telegram thin client online when the teacher is away from the terminal.

One install: `pip install clawed`. One command: `clawed`.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration model | Absorb & rebrand | Most polished result. Claw-ED owns the CLI. |
| Python-TS bridge | Subprocess (`python3 -m clawed <cmd> --json`) | Simple, reliable, keeps Python independent |
| Telegram mode | Background daemon (launchd/systemd) | Always-on for teachers throughout the day |
| NL routing | Multi-provider tool_use | Teacher picks provider; LLM picks tools |
| Install method | `pip install clawed` | One command. Pre-built cli.js bundled in wheel. |
| Build tool | Bun (existing) | Don't fix what works |
| Repo name | Claw-ED (drop v0920) | Clean naming for v3 |

## Architecture

### Repo Structure

```
Claw-ED/
├── cli/                          # Absorbed Claude Code source (TypeScript)
│   ├── source/src/
│   │   ├── constants/
│   │   │   ├── product.ts        # "Claw-ED" branding, URLs
│   │   │   ├── figures.ts        # Claw-ED icons/symbols
│   │   │   └── logo.ts           # NEW: Professional ASCII logo + animation
│   │   ├── utils/
│   │   │   └── theme.ts          # Educational color palette
│   │   ├── services/
│   │   │   └── llm-router.ts     # NEW: Multi-provider LLM routing
│   │   ├── tools/clawed/         # NEW: 14 Claw-ED tools
│   │   │   ├── LessonTool.ts
│   │   │   ├── GameTool.ts
│   │   │   ├── IngestTool.ts
│   │   │   ├── TrainTool.ts
│   │   │   ├── ExportTool.ts
│   │   │   ├── UnitTool.ts
│   │   │   ├── AssessmentTool.ts
│   │   │   ├── StandardsTool.ts
│   │   │   ├── PersonaTool.ts
│   │   │   ├── DifferentiateTool.ts
│   │   │   ├── ReviewTool.ts
│   │   │   ├── SearchCurriculumTool.ts
│   │   │   ├── MaterialsTool.ts
│   │   │   └── StudentsTool.ts
│   │   ├── commands/clawed/      # NEW: Claw-ED commands
│   │   │   ├── daemon.ts         # daemon start/stop/status/logs
│   │   │   ├── setup.ts          # Onboarding wizard
│   │   │   └── status.ts         # System status dashboard
│   │   ├── components/
│   │   │   ├── ClawedLogo.tsx    # NEW: Animated ASCII logo component
│   │   │   └── ClawedStartup.tsx # NEW: Startup animation sequence
│   │   └── entrypoints/
│   │       └── cli.tsx           # Modified entry point
│   ├── scripts/build-cli.mjs     # Build → cli.js
│   └── package.json              # name: "clawed"
│
├── clawed/                       # Python engine (existing, preserved)
│   ├── cli.py                    # Entry point: detects Node → JS or fallback typer
│   ├── ... (all existing modules unchanged)
│   └── _json_output.py           # NEW: --json flag support for all commands
│
├── daemon/                       # NEW: Background daemon
│   ├── index.ts                  # Daemon entry point
│   ├── telegram-bridge.ts        # Telegram message → Python subprocess
│   ├── process-manager.ts        # PID management, auto-restart
│   └── launchd/
│       └── com.clawed.daemon.plist  # macOS service definition
│
├── tests/                        # Python tests (existing 1609+)
├── cli-tests/                    # NEW: TypeScript integration tests
│   ├── tools/                    # Test each tool bridge
│   └── e2e/                      # End-to-end CLI tests
│
├── pyproject.toml                # version: "3.0.0"
├── package.json                  # Root workspace coordinator
├── README.md                     # Rewritten for v3
├── CHANGELOG.md                  # v3.0.0 entry
└── docs/
    └── (updated documentation)
```

### Component Diagram

```
┌─────────────────────────────────────────────────────┐
│                   TEACHER                            │
│          (terminal or Telegram phone)                │
└──────────┬──────────────────────┬───────────────────┘
           │                      │
    ┌──────▼──────┐       ┌──────▼──────┐
    │  Ink TUI    │       │  Telegram   │
    │  (primary)  │       │ (thin client)│
    │  TypeScript │       │  via daemon  │
    └──────┬──────┘       └──────┬──────┘
           │                      │
    ┌──────▼──────────────────────▼──────┐
    │       Multi-Provider LLM Router    │
    │  (reads ~/.eduagent/config.json)   │
    │  Anthropic│OpenAI│Gemini│Ollama    │
    │       ↕ tool_use / fn_calling      │
    └──────────────┬─────────────────────┘
                   │
    ┌──────────────▼─────────────────────┐
    │      Claw-ED Tool Layer (TS)       │
    │  14 tools registered with LLM     │
    │  Each spawns subprocess:           │
    │  python3 -m clawed <cmd> --json    │
    └──────────────┬─────────────────────┘
                   │
    ┌──────────────▼─────────────────────┐
    │      Python Engine (clawed/)       │
    │  Lesson │ Game │ Export │ Ingest   │
    │  Standards │ Persona │ Memory     │
    │  Differentiation │ Assessment     │
    │  Image Pipeline │ MCP Server      │
    └────────────────────────────────────┘
```

### Data Flow: Natural Language Lesson Request

```
Teacher types: "make me a lesson on the causes of WWI for 8th grade"
  │
  ▼
Ink TUI captures input → sends to LLM (teacher's configured provider)
  │
  ▼
LLM returns tool_use: generate_lesson(topic="Causes of WWI", grade="8", subject="US History")
  │
  ▼
LessonTool.ts spawns: python3 -m clawed gen lesson "Causes of WWI" -g 8 -s "US History" --json
  │
  ▼
Python engine:
  1. Loads persona from ~/.eduagent/persona.json
  2. Loads standards for NY grade 8 US History
  3. Builds system prompt with persona + standards + subject skill
  4. Calls LLM (DEEP tier) → MasterContent JSON
  5. Exports to DOCX (student handout + teacher plan)
  6. Runs quality review (score 0-10)
  7. Returns JSON: {status, files: [paths], score, master_content}
  │
  ▼
LessonTool.ts parses JSON → renders in Ink TUI:
  - "Lesson generated: Causes of WWI (Score: 8.7/10)"
  - "Files: ~/clawed_output/causes_of_wwi_handout.docx"
  - "        ~/clawed_output/causes_of_wwi_plan.docx"
  │
  ▼
LLM sees result → responds naturally:
  "Your lesson on the causes of WWI is ready. The student handout and
   teacher plan are saved. Quality score: 8.7/10. Want me to also
   generate slides or a game for this lesson?"
```

## Branding

### Product Identity

- **Name:** Claw-ED
- **Tagline:** Your AI co-teacher
- **Binary:** `clawed`
- **PyPI package:** `clawed`
- **GitHub:** SirhanMacx/Claw-ED

### Color Palette

| Role | Color | Hex | Usage |
|------|-------|-----|-------|
| Primary accent | Warm Gold | `#D4A843` | Highlights, active elements, logo |
| Secondary | Deep Green | `#2D5F3C` | Headers, borders, success states |
| Background (dark) | Chalkboard | `#1A3A2A` | Dark theme background |
| Background (light) | Cream | `#FFF8E7` | Light theme background |
| Text (dark theme) | Chalk White | `#F5F0E8` | Primary text on dark |
| Error | Apple Red | `#C1392B` | Errors, critical alerts |
| Info | Slate Blue | `#4A6FA5` | Informational, links |
| Warm accent | Terracotta | `#C17B4A` | Secondary highlights |

### ASCII Logo

Professional, detailed ASCII art of an apple with claws, wearing a graduation cap, clutching a rolled diploma. Clean lines, no emoji. Multiple sizes:

- **Full logo:** ~15 lines tall, used at startup with animation
- **Compact logo:** ~5 lines tall, used in headers/about screen
- **Inline mark:** Single-line `[🍎]` for status bar (only emoji use)

### Startup Animation

1. Logo draws in line-by-line (typewriter effect, ~1.5s)
2. "Claw-ED" text appears below in warm gold (fade-in, ~0.5s)
3. "Your AI co-teacher" subtitle fades in below (~0.3s)
4. Brief pause (~0.5s)
5. Transition to REPL prompt

Total startup animation: ~3 seconds. Skippable with any keypress.

## Subsystem Details

### 1. Subprocess Bridge Protocol

Every Python command gains a `--json` flag via a new `clawed/_json_output.py` module:

```python
# _json_output.py
import json
import sys
from contextlib import contextmanager

@contextmanager
def json_output():
    """Capture output as JSON instead of rich console."""
    result = {"status": "success", "data": None, "errors": []}
    try:
        yield result
    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))
    finally:
        json.dump(result, sys.stdout)
        sys.stdout.flush()
```

Each command wrapper checks for `--json` and routes accordingly:
- With `--json`: structured JSON to stdout, no rich formatting
- Without `--json`: existing rich console output (backward compatible)

**Universal JSON Envelope:**

Every command returns this shape:

```json
{
  "status": "success" | "error",
  "command": "gen.lesson",
  "data": { ... },
  "files": ["/path/to/output.docx"],
  "warnings": [],
  "errors": []
}
```

**Per-Command `data` Schemas:**

| Command | `data` contents |
|---------|----------------|
| `gen lesson` | `{title, subject, grade, topic, score, master_content: MasterContent}` |
| `gen unit` | `{title, subject, grade, weeks, daily_lessons: LessonBrief[]}` |
| `gen materials` | `{title, items: MaterialItem[]}` |
| `game create` | `{title, html_path, mechanic, score}` |
| `assessment` | `{title, type, questions: Question[]}` |
| `gen ingest` | `{documents_count, images_count, persona_extracted: bool}` |
| `export` | `{format, output_path}` |
| `train` | `{mode, lessons_generated, avg_score, scores: float[]}` |
| `config standards` | `{state, subject, standards: Standard[]}` |
| `config persona` | `{persona: TeacherPersona}` |
| `differentiate` | `{student, modifications: Modification[]}` |
| `review` | `{score, issues: Issue[], passed: bool}` |
| `search` | `{query, results: Document[]}` |
| `students` | `{profiles: StudentProfile[]}` |

These map 1:1 to the existing Pydantic models in `clawed/models.py`. The `--json` flag calls `.model_dump()` on the result rather than rendering with Rich.

**This is Phase 0** — the `--json` retrofit is the serial dependency that everything else builds on. It must be complete before any TypeScript tool can be implemented.

**TypeScript tool template:**

```typescript
// tools/clawed/LessonTool.ts
import { spawn } from 'child_process';

export const LessonTool: Tool = {
  name: 'generate_lesson',
  description: 'Generate a complete lesson plan with student handout',
  inputSchema: z.object({
    topic: z.string().describe('The lesson topic'),
    grade: z.string().describe('Grade level (e.g., "8")'),
    subject: z.string().describe('Subject area (e.g., "US History")'),
    format: z.enum(['docx', 'pptx', 'pdf']).default('docx'),
  }),
  async call(input, context) {
    const args = [
      '-m', 'clawed', 'gen', 'lesson', input.topic,
      '-g', input.grade,
      '-s', input.subject,
      '--format', input.format,
      '--json',
    ];
    const result = await spawnPython(args);
    return formatToolResult(result);
  },
};
```

**Subprocess Error Handling (`spawnPython` implementation):**

```typescript
// tools/clawed/_bridge.ts
async function spawnPython(args: string[], opts?: { timeout?: number }): Promise<BridgeResult> {
  const timeout = opts?.timeout ?? TIMEOUT_BY_COMMAND[args[2]] ?? 120_000;

  // Verify Python is available (cached after first check)
  if (!pythonPath) {
    pythonPath = await findPython(); // checks python3, python, validates >= 3.10
    if (!pythonPath) throw new BridgeError('Python 3.10+ not found. Install from python.org');
  }

  const proc = spawn(pythonPath, args, { timeout });
  let stdout = '', stderr = '';

  proc.stdout.on('data', (d) => stdout += d);
  proc.stderr.on('data', (d) => stderr += d);

  const code = await new Promise<number>((resolve, reject) => {
    proc.on('close', resolve);
    proc.on('error', reject);
  });

  if (code !== 0) {
    return { status: 'error', errors: [stderr || `Process exited with code ${code}`], data: null, files: [] };
  }

  try {
    return JSON.parse(stdout);
  } catch {
    return { status: 'error', errors: [`Invalid JSON output: ${stdout.slice(0, 200)}`], data: null, files: [] };
  }
}

// Timeout tiers (ms)
const TIMEOUT_BY_COMMAND: Record<string, number> = {
  'lesson': 120_000,   // 2 min — LLM generation
  'unit': 180_000,     // 3 min — multi-lesson planning
  'game': 120_000,     // 2 min — game compilation
  'ingest': 300_000,   // 5 min — large file ingestion
  'train': 600_000,    // 10 min — benchmark runs
  'export': 60_000,    // 1 min — file export
  'standards': 5_000,  // 5 sec — local lookup
  'persona': 5_000,    // 5 sec — local read
  'review': 30_000,    // 30 sec — quality check
};
```
```

### 2. Multi-Provider LLM Router (TypeScript)

**Two routers, two responsibilities:**

| Layer | Router | Purpose | Config Key |
|-------|--------|---------|-----------|
| Conversational | TS `llm-router.ts` | NL intent → tool_use selection | `config.provider` |
| Generation | Python `model_router.py` | Lesson/game/assessment content | `config.provider` (same) |

Both read from `~/.eduagent/config.json` and use the **same provider**. The distinction is:
- The TS router handles the conversational REPL (deciding which tool to call)
- The Python router handles generation-tier calls (creating the actual lesson content, always DEEP tier)

There is NO `chat_provider` vs `generation_provider` split. One provider, one config. The TS router picks the conversational model (WORK tier for tool selection), Python picks DEEP tier for generation. Both use the same provider's API key.

```typescript
// services/llm-router.ts
interface LLMRouter {
  provider: 'anthropic' | 'openai' | 'google' | 'ollama' | string;
  model: string;
  apiKey: string;

  // Route a message with tool definitions to the configured provider
  chat(messages: Message[], tools: ToolDef[]): AsyncGenerator<Chunk>;
}
```

Reads `~/.eduagent/config.json` at startup. Maps provider to SDK:
- `anthropic` → `@anthropic-ai/sdk` (tool_use)
- `openai` → `openai` npm package (function_calling)
- `google` → `@google/generative-ai` (function_calling)
- `ollama` → HTTP to localhost:11434 (native tool_use, requires Ollama 0.3.0+; older versions without tool support get a helpful error message telling teacher to update)

**Auth chain (priority order, highest first):**
1. Environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.)
2. `~/.claude/.credentials.json` (Claude Code OAuth tokens, sk-ant-oat01-*)
3. OS keychain (macOS Keychain / Linux Secret Service)
4. `~/.eduagent/secrets.json` (chmod 600)

This matches the Python `config.py` precedence exactly. Both TS and Python resolve auth the same way.

**Config isolation:** Claw-ED uses ONLY `~/.eduagent/` for its config. The `~/.claude/` directory is read-only (for OAuth token discovery) but never written to. No Claw-ED config lives in `~/.claude/`.

### 3. Background Daemon

```typescript
// daemon/index.ts
class ClawedDaemon {
  private telegramBridge: TelegramBridge;
  private pidFile = '~/.eduagent/daemon.pid';
  private logFile = '~/.eduagent/daemon.log';

  async start() {
    writePid();
    this.telegramBridge = new TelegramBridge(config.telegramToken);
    await this.telegramBridge.startPolling();
    log('Daemon started, Telegram bot online');
  }

  async stop() {
    await this.telegramBridge.stopPolling();
    removePid();
  }
}
```

**TelegramBridge** wraps `node-telegram-bot-api`:
- Receives message → routes through the **same TS LLM router** used by the Ink TUI
- The daemon imports `LLMRouter` from `services/llm-router.ts` (shared code)
- LLM sees the same 14 Claw-ED tools → picks the right one → subprocess to Python
- Results sent back as Telegram messages + file attachments
- Long-running operations show "generating..." status with Telegram `sendChatAction('typing')`

**Telegram NL routing flow:**
```
Telegram message → TelegramBridge
  → LLMRouter.chat(message, clawedTools)  # Same router as Ink TUI
  → LLM returns tool_use → spawn python3 -m clawed <cmd> --json
  → Parse result → Telegram reply + file upload
```

**Security:**
- Telegram bot only responds to the configured teacher's Telegram user ID
- Teacher ID stored in `~/.eduagent/config.json` as `telegram_user_id`
- Set during onboarding or via `clawed config telegram`
- Unknown users get: "This is a private teaching assistant. Contact your administrator."
- Rate limit: max 10 requests/minute per user (prevents abuse if bot token leaks)
- Restricted commands via Telegram: `config`, `daemon`, `setup` are terminal-only (blocked from Telegram)

**Service management:**
- macOS: launchd plist at `~/Library/LaunchAgents/com.clawed.daemon.plist`
- Linux: systemd user unit at `~/.config/systemd/user/clawed-daemon.service`
- `clawed daemon start` registers + starts the service
- `clawed daemon stop` stops + unregisters
- `clawed daemon status` shows running/stopped, uptime, last Telegram activity
- `clawed daemon logs [-f]` tails the log file

### 4. Branding Changes in Claude Code Source

Files to modify in `cli/source/src/`:

| File | Change |
|------|--------|
| `constants/product.ts` | "Claude Code" → "Claw-ED", URLs → Claw-ED URLs |
| `constants/figures.ts` | Replace crab/Claude icons with apple-claw icons |
| `constants/logo.ts` | NEW: ASCII logo data + animation frames |
| `utils/theme.ts` | Replace color palette with educational colors |
| `components/App.tsx` | Replace startup branding |
| `components/ClawedLogo.tsx` | NEW: Animated logo React component |
| `components/ClawedStartup.tsx` | NEW: Startup animation sequence |
| `entrypoints/cli.tsx` | Update binary name, startup flow |
| `main.tsx` | Add Claw-ED tool registration, config loading |
| `tools.ts` | Register 14 Claw-ED tools alongside built-in tools |
| `commands.ts` | Add daemon, setup, status commands |
| `package.json` | name → "clawed", bin → "clawed" |

### 5. Python Entry Point Modification

```python
# clawed/cli.py (modified)
import shutil
import subprocess
import sys

def main():
    """Entry point for `clawed` command."""
    # Check if we should launch the TypeScript CLI
    node = shutil.which('node')
    cli_js = _find_bundled_cli_js()

    if node and cli_js and '--python' not in sys.argv:
        # Launch the beautiful Ink TUI
        result = subprocess.run([node, cli_js] + sys.argv[1:])
        sys.exit(result.returncode)
    else:
        # Fallback to Python typer CLI
        from clawed._typer_app import app
        app()
```

The existing typer app moves to `clawed/_typer_app.py` (renamed from current `cli.py` logic). The new `cli.py` is a thin router.

### 6. Packaging

**pyproject.toml changes:**

```toml
[project]
name = "clawed"
version = "3.0.0"

[project.scripts]
clawed = "clawed.cli:main"

[tool.setuptools.package-data]
clawed = ["_cli_bundle/cli.js"]
```

**Build pipeline:**
1. `cd cli && bun scripts/build-cli.mjs` → produces `cli/dist/cli.js`
2. Copy `cli/dist/cli.js` → `clawed/_cli_bundle/cli.js`
3. `python -m build` → wheel includes the bundled JS
4. `twine upload dist/*` → PyPI

**GitHub Actions CI:**
1. Run Python tests (1609+)
2. Build TypeScript CLI
3. Run TypeScript integration tests
4. Build wheel with bundled CLI
5. Upload to PyPI on tag push

## Feature Preservation Matrix

All 16 features from v2.5.3. **14 get dedicated TS tools; 3 are Python-internal** (Image Pipeline, Memory & Feedback, MCP Server don't need TS tool wrappers because they're invoked internally by other commands, not directly by teachers).

| # | Feature | Python Module | TS Tool | Status |
|---|---------|--------------|---------|--------|
| 1 | OAuth Authentication | agent.py, config.py | llm-router.ts | Preserved + extended |
| 2 | Lesson Generation | lesson.py, master_content.py | LessonTool.ts | Preserved |
| 3 | Persona & Voice | persona.py, models.py | PersonaTool.ts | Preserved |
| 4 | Curriculum Ingestion | ingestor.py | IngestTool.ts | Preserved |
| 5 | Export System | export_docx/pptx/pdf.py | ExportTool.ts | Preserved |
| 6 | Image Pipeline | slide_images.py, image_pipeline.py | (internal to Python) | Preserved |
| 7 | Interactive Games | compile_game.py | GameTool.ts | Preserved |
| 8 | Output Quality Review | review_output.py | ReviewTool.ts | Preserved |
| 9 | Model Router | model_router.py | llm-router.ts | Preserved + extended |
| 10 | Standards System | standards.py | StandardsTool.ts | Preserved |
| 11 | Differentiation | differentiation.py | DifferentiateTool.ts | Preserved |
| 12 | Memory & Feedback | memory_engine.py, feedback.py | (internal to Python) | Preserved |
| 13 | Continuous Improvement | improver.py, train command | TrainTool.ts | Preserved |
| 14 | Telegram Bot | transports/telegram.py | daemon/telegram-bridge.ts | Rearchitected (daemon) |
| 15 | MCP Server | mcp_server.py | (still available) | Preserved |
| 16 | Onboarding | onboarding.py | commands/setup.ts | Rearchitected (Ink TUI) |

## Known Issues to Fix

1. **PPTX vocabulary overcrowding** — Split >4 terms across multiple slides in `export_pptx.py`
2. **PPTX visual theming** — Match slide theme to lesson topic (nautical for exploration, etc.)
3. **Game HTML structural repair** — Prevention-first: only use code-capable models for game generation
4. **Rate limit handling** — TypeScript CLI retries with backoff on 429, falls back to lower tier

## Migration from v2.5.3

**Data compatibility:** v3.0 reads the same `~/.eduagent/` directory layout as v2.5.3. No migration needed for:
- `config.json` — same schema, new fields added (backward compatible)
- `secrets.json` — unchanged
- `persona.json` / `persona_deep.md` — unchanged
- `curriculum_state.json` — unchanged
- `jon_curriculum_cache/` — unchanged (668MB stays in place)

**New fields added to config.json:**
- `telegram_user_id` — for daemon security (optional, set during onboarding)
- `version` — "3.0.0" (for future migration checks)

**Upgrade path:** `pip install --upgrade clawed` from 2.5.3 → 3.0.0 just works. No re-onboarding required. First run prints a one-time "Welcome to Claw-ED v3" message showing new features.

## Node.js Fallback Experience

When Node.js is not installed:
1. Python entry point detects missing `node` binary
2. Prints one-time notice:

```
Claw-ED v3.0 — running in classic mode (Python CLI)

For the full experience with the interactive AI assistant,
install Node.js 18+: https://nodejs.org

Classic mode still supports all commands:
  clawed lesson "Topic" -g 8 -s "US History"
  clawed game create "Topic"
  clawed ingest ~/Documents/
```

3. Falls back to existing typer/rich CLI — all commands work, just without the Ink TUI and NL routing
4. This notice shows once, then sets `~/.eduagent/.node_notice_shown`

## Platform Support

| Platform | Ink TUI | Python CLI | Daemon |
|----------|---------|------------|--------|
| macOS | Full | Full | launchd |
| Linux | Full | Full | systemd |
| Windows | Full (Windows Terminal) | Full | Not supported (use WSL) |

Windows daemon support is out of scope for v3.0. Windows teachers can use the Ink TUI and Python CLI but not the always-on Telegram daemon. WSL provides a full experience including the daemon.

## Observability

**Ink TUI logging:**
- `~/.eduagent/cli.log` — debug log for the TypeScript CLI
- Set `CLAWED_LOG_LEVEL=debug` for verbose output
- Captures: tool calls, subprocess spawns, LLM router decisions, errors

**Daemon logging:**
- `~/.eduagent/daemon.log` — all daemon activity
- `clawed daemon logs -f` for live tail
- Captures: Telegram messages received/sent, subprocess results, errors

**Python logging:**
- Existing logging via `logging` module (unchanged)
- `--verbose` flag on any command for debug output

## Bundle Size

Expected cli.js bundle: ~15-25MB (Bun tree-shakes unused features). PyPI wheel total: ~20-30MB including Python code + bundled JS. Well within PyPI's 100MB limit. Comparable to packages like `tensorflow-lite` or `pytorch-cpu` in wheel size.

## Testing Strategy

**Python (existing):**
- All 1609+ tests continue to pass
- New tests for `--json` output flag on each command
- `ulimit -n 4096 && python3 -m pytest tests/ -q --tb=short`

**TypeScript (new):**
- Integration test per tool: mock Python subprocess, verify JSON parsing
- E2E test: actual Python call for critical paths (lesson, game, export)
- Branding test: no "Claude" strings in output
- Daemon test: start/stop lifecycle, Telegram message routing

## Release Checklist

1. [ ] Rename repo directory to Claw-ED
2. [ ] Copy claude-code-source-build into cli/
3. [ ] Replace all "Claude Code" branding with "Claw-ED"
4. [ ] Design professional ASCII logo with animation
5. [ ] Implement educational color palette
6. [ ] Startup animation component
7. [ ] Add --json flag to all Python commands
8. [ ] Implement 14 TypeScript tool bridges
9. [ ] Implement multi-provider LLM router (TS)
10. [ ] Implement background daemon with Telegram bridge
11. [ ] Wire Python entry point to detect Node.js → JS or fallback
12. [ ] Bundle cli.js into Python wheel
13. [ ] Natural language mode working end-to-end
14. [ ] Self-configuration (detect Ollama, API keys, persona)
15. [ ] Onboarding wizard in Ink TUI
16. [ ] Fix PPTX vocabulary overcrowding
17. [ ] Fix PPTX visual theming
18. [ ] All 1609+ Python tests pass
19. [ ] TypeScript integration tests pass
20. [ ] No "Claude" strings in user-facing output
21. [ ] README rewritten for v3
22. [ ] CHANGELOG updated with v3.0.0
23. [ ] Landing page updated
24. [ ] Subprocess bridge with timeout tiers and error handling
25. [ ] Telegram bot authorization (restrict to configured teacher)
26. [ ] Node.js absence detection with helpful fallback message
27. [ ] Bundle size audit (cli.js < 30MB, wheel < 50MB)
28. [ ] Smoke test on machine without Node.js (fallback path)
29. [ ] v2.5.3 → v3.0 upgrade path verified (pip install --upgrade)
30. [ ] Ship to PyPI as clawed 3.0.0
31. [ ] Ship to GitHub as v3.0.0 release
32. [ ] Deploy to fleet nodes
