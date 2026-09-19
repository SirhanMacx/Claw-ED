# Claw-ED v3.0 Implementation Plan

> Historical plan, superseded in v9.18.2026.1. The terminal and daemon described below have been removed. Use [the current architecture](../../ARCHITECTURE.md) for development; this document records an abandoned implementation.

**Goal:** Transform Claw-ED into a polished AI co-teacher CLI by absorbing Claude Code's source build, rebranding it, wiring all 16 Python features as TypeScript tools, adding a background Telegram daemon, and shipping to PyPI + GitHub.

**Architecture:** TypeScript Ink TUI (rebranded Claude Code) → subprocess bridge → Python engine (unchanged). Multi-provider LLM router for conversational layer. Background daemon for always-on Telegram. Single `pip install clawed` installs everything.

**Tech Stack:** TypeScript (Bun, Ink/React, zod), Python (typer, pydantic, rich), node-telegram-bot-api, launchd/systemd

**Spec:** `docs/superpowers/specs/2026-04-01-v3-clawed-cli-design.md`

---

## Phase 0: JSON Bridge (Serial Dependency)

Everything depends on Python commands outputting structured JSON. This must be complete before any TypeScript tool work begins.

### Task 0.1: Create the JSON Output Infrastructure

**Files:**
- Create: `clawed/_json_output.py`
- Create: `tests/test_json_output.py`

- [ ] **Step 1: Write the test for the JSON envelope**

```python
# tests/test_json_output.py
import json
import subprocess
import sys

def test_json_envelope_success():
    """JSON output wraps successful results in standard envelope."""
    from clawed._json_output import json_envelope
    result = json_envelope("gen.lesson", data={"title": "WWI"}, files=["/tmp/out.docx"])
    assert result["status"] == "success"
    assert result["command"] == "gen.lesson"
    assert result["data"]["title"] == "WWI"
    assert result["files"] == ["/tmp/out.docx"]
    assert result["errors"] == []
    assert result["warnings"] == []

def test_json_envelope_error():
    """JSON output wraps errors properly."""
    from clawed._json_output import json_envelope
    result = json_envelope("gen.lesson", status="error", errors=["API key missing"])
    assert result["status"] == "error"
    assert result["errors"] == ["API key missing"]

def test_json_envelope_serializable():
    """Envelope is JSON-serializable."""
    from clawed._json_output import json_envelope
    result = json_envelope("test", data={"nested": {"key": "val"}})
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    roundtrip = json.loads(serialized)
    assert roundtrip["data"]["nested"]["key"] == "val"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/Claw-ED-v0920 && python3 -m pytest tests/test_json_output.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'clawed._json_output'"

- [ ] **Step 3: Implement the JSON output module**

```python
# clawed/_json_output.py
"""Structured JSON output for CLI commands.

Every command that supports --json uses this module to produce
a standard envelope: {status, command, data, files, warnings, errors}.
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any


def json_envelope(
    command: str,
    *,
    status: str = "success",
    data: Any = None,
    files: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Build a standard JSON envelope."""
    return {
        "status": status,
        "command": command,
        "data": data,
        "files": files or [],
        "warnings": warnings or [],
        "errors": errors or [],
    }


def emit_json(envelope: dict[str, Any]) -> None:
    """Write JSON envelope to stdout and flush."""
    json.dump(envelope, sys.stdout, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


def run_json_command(command: str, fn, **kwargs) -> None:
    """Run a function and emit its result as JSON.

    fn must return a dict with optional keys: data, files, warnings.
    On exception, emits error envelope.
    """
    try:
        result = fn(**kwargs)
        if result is None:
            result = {}
        envelope = json_envelope(
            command,
            data=result.get("data"),
            files=result.get("files", []),
            warnings=result.get("warnings", []),
        )
    except Exception as e:
        envelope = json_envelope(
            command,
            status="error",
            errors=[str(e), traceback.format_exc()],
        )
    emit_json(envelope)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Projects/Claw-ED-v0920 && python3 -m pytest tests/test_json_output.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add clawed/_json_output.py tests/test_json_output.py
git commit -m "feat: add JSON output infrastructure for CLI bridge"
```

---

### Task 0.2: Add --json Flag to the Lesson Command

**Files:**
- Modify: `clawed/commands/generate.py` (the `lesson` function)
- Modify: `tests/test_json_output.py`

- [ ] **Step 1: Write the integration test**

```python
# Add to tests/test_json_output.py
import subprocess
import json

def test_lesson_json_flag_error_without_config():
    """clawed gen lesson --json returns error envelope when not configured."""
    result = subprocess.run(
        [sys.executable, "-m", "clawed", "gen", "lesson", "Test Topic", "-g", "8", "-s", "US History", "--json"],
        capture_output=True, text=True, timeout=30,
    )
    output = json.loads(result.stdout)
    assert output["command"] == "gen.lesson"
    assert output["status"] in ("success", "error")
    assert isinstance(output["data"], (dict, type(None)))
    assert isinstance(output["files"], list)
    assert isinstance(output["errors"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/Claw-ED-v0920 && python3 -m pytest tests/test_json_output.py::test_lesson_json_flag_error_without_config -v`
Expected: FAIL (--json flag not recognized)

- [ ] **Step 3: Add --json flag to the lesson command**

In `clawed/commands/generate.py`, find the `lesson` function and add the `json_output` parameter. The pattern is:

```python
# Add import at top of generate.py
from clawed._json_output import run_json_command, emit_json, json_envelope

# Modify the lesson function signature to add --json flag:
# Find: def lesson(
# Add this parameter alongside existing ones:
#   json_output: bool = typer.Option(False, "--json", help="Output as JSON"),

# Then wrap the function body:
# if json_output:
#     run_json_command("gen.lesson", _lesson_json, topic=topic, grade=grade, subject=subject, fmt=fmt, ...)
#     return
# ... existing code unchanged ...
```

Create the JSON-mode helper that returns structured data instead of printing to console:

```python
def _lesson_json(*, topic, grade, subject, fmt, unit_file=None, lesson_number=1):
    """Run lesson generation and return structured result for JSON output."""
    import asyncio
    from clawed.config import load_config
    from clawed.lesson import generate_lesson

    config = load_config()
    # Run the async generation
    loop = asyncio.new_event_loop()
    try:
        lesson_result = loop.run_until_complete(
            generate_lesson(topic=topic, grade=grade, subject=subject, config=config)
        )
    finally:
        loop.close()

    # Export to file
    output_path = None
    if lesson_result:
        from clawed.io import save_output
        output_path = save_output(lesson_result, fmt=fmt)

    return {
        "data": lesson_result.model_dump() if lesson_result else None,
        "files": [str(output_path)] if output_path else [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Projects/Claw-ED-v0920 && python3 -m pytest tests/test_json_output.py::test_lesson_json_flag_error_without_config -v`
Expected: PASS (returns valid JSON envelope even if generation fails due to missing API key)

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd ~/Projects/Claw-ED-v0920 && ulimit -n 4096 && python3 -m pytest tests/ -q --tb=short -x`
Expected: All 1609+ tests pass

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add clawed/commands/generate.py tests/test_json_output.py
git commit -m "feat: add --json flag to lesson command"
```

---

### Task 0.3: Add --json Flag to Remaining Generation Commands

**Files:**
- Modify: `clawed/commands/generate.py` (ingest function)
- Modify: `clawed/commands/generate_unit.py` (unit function)
- Modify: `clawed/commands/generate_assessment.py` (materials, assess functions)
- Modify: `clawed/commands/game.py` (create function)
- Modify: `clawed/commands/export.py` (export_cmd function)
- Modify: `clawed/commands/train.py` (train function)
- Modify: `clawed/commands/config.py` (config_show, stats functions)
- Modify: `clawed/commands/config_profile.py` (persona_show, standards_list functions)
- Create: `tests/test_json_commands.py`

Apply the same pattern from Task 0.2 to each command. For each command:

1. Add `json_output: bool = typer.Option(False, "--json", help="Output as JSON")` parameter
2. Create `_<command>_json()` helper that returns `{data, files, warnings}` dict — use existing `_run_async()` from `_helpers.py` instead of creating new event loops
3. At the top of the command function: `if json_output: run_json_command("<cmd>", _<cmd>_json, ...); return`
4. Existing console output code stays untouched (the `else` path)

**NOTE: Missing CLI commands that need creation first:**
- `review` — no CLI command exists. Add `review` to `generate.py` or a new `review_cmd.py` that wraps `review_output.py`'s `review_pptx()` / `review_docx()` / `review_game_html()`.
- `search` — no CLI command exists. Add `search` to `generate.py` or a new `search_cmd.py` that wraps the corpus/memory search functions.
- `differentiate` — exists at `generate.py` but may need `--json` wiring.
- `workspace students` — exists at `workspace_cmd.py`, add `--json`.

- [ ] **Step 1: Write tests for all JSON-flagged commands**

```python
# tests/test_json_commands.py
"""Test --json flag on all commands that support it."""
import json
import subprocess
import sys
import pytest

COMMANDS_WITH_JSON = [
    (["gen", "ingest", "/tmp/nonexistent", "--json"], "gen.ingest"),
    (["gen", "unit", "Test", "-g", "8", "-s", "US History", "--json"], "gen.unit"),
    (["gen", "materials", "--json"], "gen.materials"),
    (["game", "create", "Test", "--json"], "game.create"),
    (["train", "--benchmark", "-n", "0", "--json"], "train"),
    (["config", "show", "--json"], "config.show"),
]

@pytest.mark.parametrize("args,expected_command", COMMANDS_WITH_JSON)
def test_json_flag_produces_valid_envelope(args, expected_command):
    """Every command with --json returns a valid JSON envelope."""
    result = subprocess.run(
        [sys.executable, "-m", "clawed"] + args,
        capture_output=True, text=True, timeout=30,
    )
    # Must produce valid JSON on stdout
    output = json.loads(result.stdout)
    assert output["command"] == expected_command
    assert output["status"] in ("success", "error")
    assert isinstance(output["files"], list)
    assert isinstance(output["errors"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/Claw-ED-v0920 && python3 -m pytest tests/test_json_commands.py -v`
Expected: FAIL (--json not recognized on most commands)

- [ ] **Step 3: Add --json flag to each command**

Apply the pattern from Task 0.2 to each command listed above. Each command gets:
1. The `json_output` parameter
2. A `_<cmd>_json()` helper
3. Early return with `run_json_command()` when `--json` is set

Key per-command data shapes:
- `gen.ingest`: `{data: {documents_count, images_count, persona_extracted}, files: []}`
- `gen.unit`: `{data: {title, subject, grade, weeks, daily_lessons}, files: [unit_json_path]}`
- `gen.materials`: `{data: {title, items}, files: [materials_path]}`
- `game.create`: `{data: {title, mechanic}, files: [html_path]}`
- `train`: `{data: {mode, lessons_generated, avg_score, scores}, files: [report_path]}`
- `config.show`: `{data: config.model_dump(), files: []}`
- `config persona show`: `{data: {persona: persona.model_dump()}, files: []}`
- `config standards list`: `{data: {standards: [(code, desc, band)]}, files: []}`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/Claw-ED-v0920 && python3 -m pytest tests/test_json_commands.py -v`
Expected: PASS (all parametrized tests)

- [ ] **Step 5: Run full test suite**

Run: `cd ~/Projects/Claw-ED-v0920 && ulimit -n 4096 && python3 -m pytest tests/ -q --tb=short -x`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add clawed/commands/ tests/test_json_commands.py
git commit -m "feat: add --json flag to all generation, config, and utility commands"
```

---

## Phase 1: Repo Setup & Branding

### Task 1.1: Copy Claude Code Source Build Into Repo

**Files:**
- Create: `cli/` (entire directory)
- Modify: `.gitignore`

- [ ] **Step 1: Copy the source build**

```bash
cd ~/Projects/Claw-ED-v0920
cp -R ~/Projects/claude-code-source-build/ cli/
rm -rf cli/.git  # Remove the nested git repo
```

- [ ] **Step 2: Update .gitignore**

Add to `.gitignore`:
```
cli/node_modules/
cli/dist/
cli/.bun/
cli/source/cli.js
cli/source/cli.js.map
```

- [ ] **Step 3: Verify the source build compiles**

```bash
cd ~/Projects/Claw-ED-v0920/cli
npm install  # or bun install
node scripts/build-cli.mjs
```
Expected: Build succeeds, produces `source/cli.js`

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/ .gitignore
git commit -m "feat: absorb claude-code-source-build into cli/"
```

---

### Task 1.2: Rebrand Product Constants

**Files:**
- Modify: `cli/source/src/constants/product.ts`
- Modify: `cli/package.json`

- [ ] **Step 1: Replace product.ts branding**

In `cli/source/src/constants/product.ts`, replace:
- `PRODUCT_URL` → `'https://sirhanmacx.github.io/Claw-ED'`
- Any reference to "Claude Code" → "Claw-ED"
- Any reference to "claude.ai" URLs → Claw-ED equivalents or remove

- [ ] **Step 2: Update package.json**

In `cli/package.json`:
```json
{
  "name": "clawed",
  "description": "Claw-ED — Your AI co-teacher. Generate lessons, games, slides, and assessments from your terminal.",
  "bin": { "clawed": "cli.js" },
  "author": "SirhanMacx <jon@clawed.dev>"
}
```

- [ ] **Step 3: Global string replacement for "Claude Code"**

Search all `.ts` and `.tsx` files under `cli/source/src/` for user-facing strings containing "Claude Code" or "Claude" (excluding API SDK references) and replace with "Claw-ED".

Key files to check:
- `constants/product.ts`
- `entrypoints/cli.tsx` (version output line)
- Any help text or error messages
- `commands/` directory (help descriptions)

- [ ] **Step 4: Build and verify no "Claude Code" in output**

```bash
cd ~/Projects/Claw-ED-v0920/cli
node scripts/build-cli.mjs
node source/cli.js --version
# Expected: "X.X.X (Claw-ED)" not "Claude Code"
```

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/constants/product.ts cli/package.json
git commit -m "feat: rebrand Claude Code → Claw-ED in product constants"
```

---

### Task 1.3: Educational Color Theme

**Files:**
- Modify: `cli/source/src/utils/theme.ts`

- [ ] **Step 1: Define Claw-ED color palette**

In `theme.ts`, replace the Claude color values in all theme objects:

```typescript
// Dark theme (chalkboard)
const darkTheme: Theme = {
  claude: 'rgb(212,168,67)',          // Warm Gold #D4A843 (was Claude orange)
  claudeShimmer: 'rgb(193,123,74)',   // Terracotta #C17B4A
  permission: 'rgb(45,95,60)',        // Deep Green #2D5F3C
  permissionShimmer: 'rgb(45,95,60)',
  text: 'rgb(245,240,232)',           // Chalk White #F5F0E8
  inverseText: 'rgb(26,58,42)',       // Chalkboard #1A3A2A
  background: 'rgb(26,58,42)',        // Chalkboard #1A3A2A
  success: 'rgb(45,95,60)',           // Deep Green
  error: 'rgb(193,57,43)',            // Apple Red #C1392B
  warning: 'rgb(212,168,67)',         // Warm Gold
  // ... keep structural colors (diff, agent, rainbow) as-is
}

// Light theme (cream/parchment)
const lightTheme: Theme = {
  claude: 'rgb(166,120,30)',          // Darker Gold for light bg
  text: 'rgb(26,58,42)',             // Chalkboard text on light
  background: 'rgb(255,248,231)',     // Cream #FFF8E7
  // ... etc
}
```

- [ ] **Step 2: Build and visually verify**

```bash
cd ~/Projects/Claw-ED-v0920/cli && node scripts/build-cli.mjs && node source/cli.js
```
Expected: Gold/green color scheme visible in UI elements

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/utils/theme.ts
git commit -m "feat: educational color palette — warm gold, deep green, chalkboard"
```

---

### Task 1.4: Professional ASCII Logo & Startup Animation

**Files:**
- Create: `cli/source/src/constants/logo.ts`
- Create: `cli/source/src/components/ClawedLogo.tsx`
- Create: `cli/source/src/components/ClawedStartup.tsx`

- [ ] **Step 1: Design the ASCII logo**

```typescript
// cli/source/src/constants/logo.ts
export const CLAWED_LOGO_FULL = `
         ___________
        /           \\
       /  _       _  \\
      |  | |     | |  |
      |  |_|  ●  |_|  |
       \\    \\_____/   /
    /|  \\___________/  |\\
   / |   /  |   |  \\   | \\
  /__|__/   |   |   \\__|__\\
     ||    _|___|_    ||
     ||   |  C  L |   ||
     ||   | A  W  |   ||
     ||   | -  E  |   ||
     ||   |__D____|   ||
     /\\                /\\
    /  \\              /  \\
   /    \\────────────/    \\
  ╱______╲__________╱______╲
`

export const CLAWED_LOGO_COMPACT = `
    🎓 ╭─────────╮
   ╱  ╱ ●  Claw  ╲  ╲
  ╱__╱___-ED______╲__╲
     ╲╱          ╲╱
`

// Animation frames — logo builds up line by line
export const CLAWED_LOGO_FRAMES: string[][] = [
  // Frame 0: just the top
  ['         ___________'],
  // Frame 1: top + cap
  ['         ___________', '        /           \\'],
  // ... each frame adds one more line
  // Final frame: full logo
]
```

Note: The actual logo design will be refined during implementation to look professional. The above is a placeholder structure. The implementer should create a polished apple-with-claws design using box-drawing characters (─ │ ╭ ╮ ╰ ╯ ╱ ╲) for clean lines.

- [ ] **Step 2: Create the animated logo React component**

```typescript
// cli/source/src/components/ClawedLogo.tsx
import React, { useState, useEffect } from 'react'
import { Text, Box } from '../ink/index.js'
import { CLAWED_LOGO_FRAMES } from '../constants/logo.js'

export function ClawedLogo({ onComplete }: { onComplete: () => void }) {
  const [frame, setFrame] = useState(0)
  const totalFrames = CLAWED_LOGO_FRAMES.length

  useEffect(() => {
    if (frame >= totalFrames) {
      // Animation complete, show tagline then callback
      const timer = setTimeout(onComplete, 800)
      return () => clearTimeout(timer)
    }
    const timer = setTimeout(() => setFrame(f => f + 1), 100) // 100ms per line
    return () => clearTimeout(timer)
  }, [frame])

  const lines = CLAWED_LOGO_FRAMES[Math.min(frame, totalFrames - 1)]

  return (
    <Box flexDirection="column" alignItems="center">
      {lines.map((line, i) => (
        <Text key={i} color="rgb(212,168,67)">{line}</Text>
      ))}
      {frame >= totalFrames && (
        <>
          <Text bold color="rgb(212,168,67)">Claw-ED</Text>
          <Text dimColor>Your AI co-teacher</Text>
        </>
      )}
    </Box>
  )
}
```

- [ ] **Step 3: Wire startup animation into the entry point**

Find where the CLI renders its initial UI (in `main.tsx` or the REPL launcher) and add the `ClawedStartup` component that shows the logo animation before transitioning to the REPL. The animation is skippable with any keypress.

- [ ] **Step 4: Build and verify animation**

```bash
cd ~/Projects/Claw-ED-v0920/cli && node scripts/build-cli.mjs && node source/cli.js
```
Expected: Logo animates line-by-line in warm gold, then transitions to REPL

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/constants/logo.ts cli/source/src/components/ClawedLogo.tsx cli/source/src/components/ClawedStartup.tsx
git commit -m "feat: professional ASCII logo with animated startup sequence"
```

---

### Task 1.5: Replace Figures and Icons

**Files:**
- Modify: `cli/source/src/constants/figures.ts`

- [ ] **Step 1: Replace Claude-specific icons**

In `figures.ts`, replace any crab/Claude-specific symbols with Claw-ED educational icons. Keep cross-platform unicode symbols (circles, arrows, diamonds) as-is — they're generic. Replace any branded spinner frames or indicators with Claw-ED equivalents.

- [ ] **Step 2: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/constants/figures.ts
git commit -m "feat: replace Claude icons with Claw-ED educational icons"
```

---

## Phase 2: TypeScript Tool Bridges

### Task 2.1: Create the Python Subprocess Bridge

**Files:**
- Create: `cli/source/src/tools/clawed/_bridge.ts`
- Create: `cli-tests/bridge.test.ts`

- [ ] **Step 1: Write the bridge test**

```typescript
// cli-tests/bridge.test.ts
import { describe, it, expect } from 'bun:test'
import { spawnPython, findPython } from '../cli/source/src/tools/clawed/_bridge.js'

describe('Python bridge', () => {
  it('finds python3 on the system', async () => {
    const python = await findPython()
    expect(python).toBeTruthy()
    expect(python).toContain('python')
  })

  it('parses JSON output from Python commands', async () => {
    const result = await spawnPython(['-c', 'import json; print(json.dumps({"status":"success","command":"test","data":null,"files":[],"errors":[],"warnings":[]}))'])
    expect(result.status).toBe('success')
    expect(result.command).toBe('test')
  })

  it('returns error envelope on Python failure', async () => {
    const result = await spawnPython(['-c', 'import sys; sys.exit(1)'], { timeout: 5000 })
    expect(result.status).toBe('error')
    expect(result.errors.length).toBeGreaterThan(0)
  })

  it('times out on long-running commands', async () => {
    const result = await spawnPython(['-c', 'import time; time.sleep(10)'], { timeout: 1000 })
    expect(result.status).toBe('error')
  })
})
```

- [ ] **Step 2: Implement the bridge**

```typescript
// cli/source/src/tools/clawed/_bridge.ts
import { spawn } from 'child_process'
import { execSync } from 'child_process'

export interface BridgeResult {
  status: 'success' | 'error'
  command: string
  data: unknown
  files: string[]
  warnings: string[]
  errors: string[]
}

const EMPTY_ERROR: BridgeResult = {
  status: 'error', command: '', data: null, files: [], warnings: [], errors: [],
}

let cachedPython: string | null = null

export async function findPython(): Promise<string | null> {
  if (cachedPython) return cachedPython
  for (const name of ['python3', 'python']) {
    try {
      const path = execSync(`which ${name}`, { encoding: 'utf-8' }).trim()
    } catch { continue }
    if (path) {
      cachedPython = path
      return path
    }
  }
  return null
}

export const TIMEOUT_BY_COMMAND: Record<string, number> = {
  lesson: 120_000,
  unit: 180_000,
  game: 120_000,
  ingest: 300_000,
  train: 600_000,
  export: 60_000,
  standards: 5_000,
  persona: 5_000,
  review: 30_000,
  materials: 120_000,
  assess: 120_000,
  differentiate: 60_000,
  search: 10_000,
  students: 5_000,
}

export async function spawnPython(
  args: string[],
  opts?: { timeout?: number },
): Promise<BridgeResult> {
  const python = await findPython()
  if (!python) {
    return { ...EMPTY_ERROR, errors: ['Python 3.10+ not found. Install from python.org'] }
  }

  const timeout = opts?.timeout ?? 120_000

  return new Promise((resolve) => {
    let stdout = ''
    let stderr = ''
    let killed = false

    const proc = spawn(python, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env },
    })

    const timer = setTimeout(() => {
      killed = true
      proc.kill('SIGTERM')
    }, timeout)

    proc.stdout.on('data', (d: Buffer) => { stdout += d.toString() })
    proc.stderr.on('data', (d: Buffer) => { stderr += d.toString() })

    proc.on('close', (code: number | null) => {
      clearTimeout(timer)

      if (killed) {
        resolve({ ...EMPTY_ERROR, errors: [`Command timed out after ${timeout}ms`] })
        return
      }

      if (code !== 0) {
        resolve({ ...EMPTY_ERROR, errors: [stderr || `Process exited with code ${code}`] })
        return
      }

      try {
        const parsed = JSON.parse(stdout.trim())
        resolve(parsed as BridgeResult)
      } catch {
        resolve({ ...EMPTY_ERROR, errors: [`Invalid JSON: ${stdout.slice(0, 500)}`] })
      }
    })

    proc.on('error', (err: Error) => {
      clearTimeout(timer)
      resolve({ ...EMPTY_ERROR, errors: [err.message] })
    })
  })
}

export function clawedArgs(command: string, subcommand: string, args: Record<string, unknown>): string[] {
  const result = ['-m', 'clawed', command, subcommand]
  for (const [key, value] of Object.entries(args)) {
    if (value === undefined || value === null || value === false) continue
    if (value === true) {
      result.push(`--${key}`)
    } else {
      result.push(`--${key}`, String(value))
    }
  }
  result.push('--json')
  return result
}
```

- [ ] **Step 3: Run tests**

```bash
cd ~/Projects/Claw-ED-v0920 && bun test cli-tests/bridge.test.ts
```
Expected: All 4 tests pass

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/tools/clawed/_bridge.ts cli-tests/bridge.test.ts
git commit -m "feat: Python subprocess bridge with timeouts and JSON parsing"
```

---

### Task 2.2: Implement the Lesson Tool

**Files:**
- Create: `cli/source/src/tools/clawed/LessonTool.ts`

This is the template for all Claw-ED tools. Other tools follow this exact pattern.

- [ ] **Step 1: Implement LessonTool**

```typescript
// cli/source/src/tools/clawed/LessonTool.ts
import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { spawnPython, clawedArgs, TIMEOUT_BY_COMMAND } from './_bridge.js'

const inputSchema = z.strictObject({
  topic: z.string().describe('The lesson topic (e.g., "Causes of World War I")'),
  grade: z.string().describe('Grade level (e.g., "8")'),
  subject: z.string().describe('Subject area (e.g., "US History", "Science", "Math")'),
  format: z.enum(['docx', 'pptx', 'pdf']).default('docx').describe('Export format'),
})

type Input = typeof inputSchema
type Output = { title: string; score: number; files: string[]; summary: string }

export const LessonTool = buildTool({
  name: 'generate_lesson',
  searchHint: 'create lesson plan handout worksheet',
  maxResultSizeChars: 50_000,

  get inputSchema() { return inputSchema },

  async description() {
    return 'Generate a complete lesson plan with student handout and teacher plan. Returns DOCX files ready for printing. Uses the teacher\'s persona, standards, and subject skills.'
  },

  async prompt() {
    return 'Generate a complete standards-aligned lesson plan. Produces a MasterContent object that exports to DOCX student handout and teacher plan. Uses the teacher\'s configured persona, state standards, and subject-specific pedagogical skills. Always routes to DEEP tier for maximum quality.'
  },

  userFacingName() { return 'Generate Lesson' },
  getActivityDescription(input) {
    return input?.topic ? `Generating lesson: ${input.topic}` : 'Generating lesson'
  },
  getToolUseSummary(input) {
    return input?.topic ? `lesson on "${input.topic}"` : 'lesson'
  },

  isConcurrencySafe() { return true },
  isReadOnly() { return false },
  toAutoClassifierInput(input) { return `generate lesson ${input.topic} ${input.subject}` },

  async checkPermissions() {
    return { behavior: 'allow' as const, updatedInput: undefined }
  },

  renderToolUseMessage(input) {
    const { Text } = require('../../ink/index.js')
    const topic = input?.topic ?? '...'
    const grade = input?.grade ?? ''
    const subject = input?.subject ?? ''
    return <Text>Generating lesson: <Text bold>{topic}</Text> (Grade {grade}, {subject})</Text>
  },

  mapToolResultToToolResultBlockParam(output, toolUseID) {
    return {
      tool_use_id: toolUseID,
      type: 'tool_result' as const,
      content: output
        ? `Lesson generated: ${output.title} (Score: ${output.score}/10)\nFiles: ${output.files.join(', ')}`
        : 'Lesson generation failed',
    }
  },

  async call(input) {
    const args = ['-m', 'clawed', 'gen', 'lesson', input.topic, '-g', input.grade, '-s', input.subject, '--format', input.format, '--json']
    const result = await spawnPython(args, { timeout: TIMEOUT_BY_COMMAND.lesson })

    if (result.status === 'error') {
      return {
        data: { title: input.topic, score: 0, files: [], summary: `Error: ${result.errors.join('; ')}` } as Output,
      }
    }

    const data = result.data as Record<string, unknown> | null
    return {
      data: {
        title: (data?.title as string) ?? input.topic,
        score: (data?.score as number) ?? 0,
        files: result.files,
        summary: `Lesson "${data?.title ?? input.topic}" generated successfully. Score: ${data?.score ?? 'N/A'}/10`,
      } as Output,
    }
  },
} satisfies ToolDef<Input, Output>)
```

- [ ] **Step 2: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/tools/clawed/LessonTool.ts
git commit -m "feat: LessonTool — TypeScript bridge for lesson generation"
```

---

### Task 2.3a: Implement Read-Only Tools (Batch A — 5 tools)

**Files:**
- Create: `cli/source/src/tools/clawed/StandardsTool.ts`
- Create: `cli/source/src/tools/clawed/PersonaTool.ts`
- Create: `cli/source/src/tools/clawed/StudentsTool.ts`
- Create: `cli/source/src/tools/clawed/SearchCurriculumTool.ts`
- Create: `cli/source/src/tools/clawed/ReviewTool.ts`

Simple read-only tools with short timeouts. Follow exact LessonTool pattern.

| Tool | Python Command | Input Schema | Timeout |
|------|---------------|--------------|---------|
| StandardsTool | `config standards list --json` | grade, subject | 5s |
| PersonaTool | `config persona show --json` | (none) | 5s |
| StudentsTool | `workspace students --json` | (none) | 5s |
| SearchCurriculumTool | `search QUERY --json` | query | 10s |
| ReviewTool | `review LESSON_FILE --json` | lesson_file | 30s |

- [ ] **Step 1: Implement all 5 tools**
- [ ] **Step 2: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/tools/clawed/StandardsTool.ts cli/source/src/tools/clawed/PersonaTool.ts cli/source/src/tools/clawed/StudentsTool.ts cli/source/src/tools/clawed/SearchCurriculumTool.ts cli/source/src/tools/clawed/ReviewTool.ts
git commit -m "feat: read-only Claw-ED tools (standards, persona, students, search, review)"
```

---

### Task 2.3b: Implement Generation Tools (Batch B — 8 tools)

**Files:**
- Create: `cli/source/src/tools/clawed/GameTool.ts`
- Create: `cli/source/src/tools/clawed/UnitTool.ts`
- Create: `cli/source/src/tools/clawed/IngestTool.ts`
- Create: `cli/source/src/tools/clawed/TrainTool.ts`
- Create: `cli/source/src/tools/clawed/ExportTool.ts`
- Create: `cli/source/src/tools/clawed/AssessmentTool.ts`
- Create: `cli/source/src/tools/clawed/DifferentiateTool.ts`
- Create: `cli/source/src/tools/clawed/MaterialsTool.ts`

Complex generation tools with longer timeouts and richer input schemas.

| Tool | Python Command | Input Schema | Timeout |
|------|---------------|--------------|---------|
| GameTool | `game create TOPIC --json` | topic, grade, subject, style?, students? | 120s |
| UnitTool | `gen unit TOPIC --json` | topic, grade, subject, weeks | 180s |
| IngestTool | `gen ingest PATH --json` | path | 300s |
| TrainTool | `train --benchmark --json` | n?, drive?, path?, full? | 600s |
| ExportTool | `export LESSON_FILE --json` | lesson_file, format | 60s |
| AssessmentTool | `assess TYPE TOPIC --json` | type, topic, grade, questions? | 120s |
| DifferentiateTool | `differentiate --json` | lesson_file, student_profiles | 60s |
| MaterialsTool | `gen materials --json` | lesson_file, format | 120s |

- [ ] **Step 1: Implement all 8 tools**
- [ ] **Step 2: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/tools/clawed/GameTool.ts cli/source/src/tools/clawed/UnitTool.ts cli/source/src/tools/clawed/IngestTool.ts cli/source/src/tools/clawed/TrainTool.ts cli/source/src/tools/clawed/ExportTool.ts cli/source/src/tools/clawed/AssessmentTool.ts cli/source/src/tools/clawed/DifferentiateTool.ts cli/source/src/tools/clawed/MaterialsTool.ts
git commit -m "feat: generation Claw-ED tools (game, unit, ingest, train, export, assess, differentiate, materials)"
```

---

### Task 2.3c: Create Index and Onboarding/Status Commands

**Files:**
- Create: `cli/source/src/tools/clawed/index.ts`
- Create: `cli/source/src/commands/clawed/setup.ts` (onboarding wizard)
- Create: `cli/source/src/commands/clawed/status.ts` (system status dashboard)

- [ ] **Step 1: Create an index file**

```typescript
// cli/source/src/tools/clawed/index.ts
export { LessonTool } from './LessonTool.js'
export { GameTool } from './GameTool.js'
export { UnitTool } from './UnitTool.js'
export { IngestTool } from './IngestTool.js'
export { TrainTool } from './TrainTool.js'
export { ExportTool } from './ExportTool.js'
export { AssessmentTool } from './AssessmentTool.js'
export { StandardsTool } from './StandardsTool.js'
export { PersonaTool } from './PersonaTool.js'
export { DifferentiateTool } from './DifferentiateTool.js'
export { ReviewTool } from './ReviewTool.js'
export { SearchCurriculumTool } from './SearchCurriculumTool.js'
export { MaterialsTool } from './MaterialsTool.js'
export { StudentsTool } from './StudentsTool.js'
```

- [ ] **Step 3: Implement setup command (onboarding wizard in Ink TUI)**

The `setup.ts` command replaces Python `onboarding.py` with an Ink TUI experience:
- Provider selection (Gemini free, Claude, OpenAI, Ollama)
- API key collection + validation
- State selection for standards
- Telegram user ID (optional, for daemon security)
- Persona detection (if `~/.eduagent/persona.json` exists)
- Config saved to `~/.eduagent/config.json`

- [ ] **Step 4: Implement status command (system dashboard)**

The `status.ts` command shows:
- Current provider + model
- Persona loaded (yes/no, name)
- Standards state
- Daemon running (yes/no, uptime)
- Curriculum cache size
- Recent lessons generated

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/tools/clawed/ cli/source/src/commands/clawed/
git commit -m "feat: tool index, onboarding wizard, and status dashboard commands"
```

---

### Task 2.4: Register Tools in tools.ts

**Files:**
- Modify: `cli/source/src/tools.ts`

- [ ] **Step 1: Import and register all Claw-ED tools**

At the top of `tools.ts`, add:
```typescript
import {
  LessonTool, GameTool, UnitTool, IngestTool, TrainTool,
  ExportTool, AssessmentTool, StandardsTool, PersonaTool,
  DifferentiateTool, ReviewTool, SearchCurriculumTool,
  MaterialsTool, StudentsTool,
} from './tools/clawed/index.js'
```

In `getAllBaseTools()`, add all 14 tools to the returned array:
```typescript
// Claw-ED tools
LessonTool,
GameTool,
UnitTool,
IngestTool,
TrainTool,
ExportTool,
AssessmentTool,
StandardsTool,
PersonaTool,
DifferentiateTool,
ReviewTool,
SearchCurriculumTool,
MaterialsTool,
StudentsTool,
```

- [ ] **Step 2: Build and verify tools are registered**

```bash
cd ~/Projects/Claw-ED-v0920/cli && node scripts/build-cli.mjs
```
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/tools.ts
git commit -m "feat: register all 14 Claw-ED tools in the tool system"
```

---

## Phase 3: Multi-Provider LLM Router

### Task 3.1: Implement the LLM Router

**Files:**
- Create: `cli/source/src/services/llm-router.ts`
- Create: `cli/source/src/services/config-reader.ts`

- [ ] **Step 1: Implement config reader**

```typescript
// cli/source/src/services/config-reader.ts
import { readFileSync, existsSync } from 'fs'
import { join } from 'path'
import { homedir } from 'os'

export interface ClawedConfig {
  provider: string
  anthropic_model?: string
  openai_model?: string
  google_model?: string
  ollama_model?: string
  export_format?: string
  teacher_profile?: {
    name: string
    school: string
    subjects: string[]
    grade_levels: string[]
    state: string
  }
}

export function readClawedConfig(): ClawedConfig | null {
  const configPath = join(homedir(), '.eduagent', 'config.json')
  if (!existsSync(configPath)) return null
  try {
    return JSON.parse(readFileSync(configPath, 'utf-8'))
  } catch {
    return null
  }
}

export function readApiKey(provider: string): string | null {
  // 1. Environment variables
  const envKeys: Record<string, string> = {
    anthropic: 'ANTHROPIC_API_KEY',
    openai: 'OPENAI_API_KEY',
    google: 'GOOGLE_API_KEY',
    ollama: 'OLLAMA_API_KEY',
  }
  const envVal = process.env[envKeys[provider] ?? '']
  if (envVal) return envVal

  // 2. Claude Code OAuth credentials
  if (provider === 'anthropic') {
    const credPath = join(homedir(), '.claude', '.credentials.json')
    if (existsSync(credPath)) {
      try {
        const creds = JSON.parse(readFileSync(credPath, 'utf-8'))
        if (creds.oauthToken) return creds.oauthToken
      } catch { /* fall through */ }
    }
  }

  // 3. Secrets file
  const secretsPath = join(homedir(), '.eduagent', 'secrets.json')
  if (existsSync(secretsPath)) {
    try {
      const secrets = JSON.parse(readFileSync(secretsPath, 'utf-8'))
      return secrets[`${provider}_api_key`] ?? secrets[envKeys[provider] ?? ''] ?? null
    } catch { /* fall through */ }
  }

  return null
}
```

- [ ] **Step 2: Implement the LLM router**

This is a substantial module. It wraps Anthropic SDK, OpenAI SDK, Google Generative AI SDK, and Ollama HTTP — selecting based on the teacher's config. The core interface:

```typescript
// cli/source/src/services/llm-router.ts
export interface ChatMessage { role: 'user' | 'assistant' | 'system'; content: string }
export interface ToolDefinition { name: string; description: string; input_schema: object }
export interface ToolCall { name: string; input: Record<string, unknown> }

export class LLMRouter {
  private provider: string
  private model: string
  private apiKey: string

  constructor(config: ClawedConfig) { /* ... */ }

  async chat(messages: ChatMessage[], tools: ToolDefinition[]): Promise<{
    text: string
    toolCalls: ToolCall[]
  }> {
    switch (this.provider) {
      case 'anthropic': return this.chatAnthropic(messages, tools)
      case 'openai': return this.chatOpenAI(messages, tools)
      case 'google': return this.chatGoogle(messages, tools)
      case 'ollama': return this.chatOllama(messages, tools)
      default: throw new Error(`Unknown provider: ${this.provider}`)
    }
  }

  // Provider-specific implementations...
}
```

The full implementation wraps each provider's SDK for tool_use. This is the most complex new TypeScript module.

**Rate limit handling:** Each provider method wraps calls with exponential backoff (retry on 429, max 3 retries, delays 1s/2s/4s).

**Ollama:** Requires Ollama 0.3.0+ for native tool_use. No prompt-injection fallback — if Ollama version is too old, show a clear error telling teacher to update.

**Keychain:** Auth chain step 3 (OS keychain) is deferred to a follow-up. Steps 1 (env), 2 (Claude OAuth), and 4 (secrets.json) cover the primary use cases. TODO comment in code for keychain integration.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add cli/source/src/services/llm-router.ts cli/source/src/services/config-reader.ts
git commit -m "feat: multi-provider LLM router (Anthropic, OpenAI, Google, Ollama)"
```

---

## Phase 4: Daemon & Telegram

### Task 4.1: Implement the Background Daemon

**Files:**
- Create: `daemon/index.ts`
- Create: `daemon/telegram-bridge.ts`
- Create: `daemon/process-manager.ts`
- Create: `daemon/launchd/com.clawed.daemon.plist`

- [ ] **Step 1: Implement process manager**

Handles PID file, logging, start/stop lifecycle.

- [ ] **Step 2: Implement Telegram bridge**

Uses `node-telegram-bot-api` for polling. Imports `LLMRouter` from the shared services. Routes NL messages through the same tool_use flow as the Ink TUI. Restricts to configured `telegram_user_id`.

- [ ] **Step 3: Implement daemon entry point**

```typescript
// daemon/index.ts
import { TelegramBridge } from './telegram-bridge.js'
import { ProcessManager } from './process-manager.js'
import { readClawedConfig, readApiKey } from '../cli/source/src/services/config-reader.js'

async function main() {
  const cmd = process.argv[2] // start | stop | status | logs
  const pm = new ProcessManager()

  switch (cmd) {
    case 'start': {
      const config = readClawedConfig()
      if (!config) { console.error('Run "clawed setup" first'); process.exit(1) }
      pm.writePid()
      const bridge = new TelegramBridge(config)
      await bridge.start()
      break
    }
    case 'stop': pm.stop(); break
    case 'status': pm.printStatus(); break
    case 'logs': pm.tailLogs(); break
  }
}
```

- [ ] **Step 4: Create launchd plist and systemd unit**

```xml
<!-- daemon/launchd/com.clawed.daemon.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.clawed.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>node</string>
        <string>DAEMON_PATH/index.js</string>
        <string>start</string>
    </array>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>LOG_PATH/daemon.log</string>
    <key>StandardErrorPath</key>
    <string>LOG_PATH/daemon.log</string>
</dict>
</plist>
```

Also create systemd user unit:
```ini
# daemon/systemd/clawed-daemon.service
[Unit]
Description=Claw-ED Teaching Assistant Daemon
After=network.target

[Service]
ExecStart=node DAEMON_PATH/index.js start
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

- [ ] **Step 5: Add daemon command to CLI**

In `cli/source/src/commands/`, add a `daemon` command that routes to the daemon entry point.

- [ ] **Step 6: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add daemon/ cli/source/src/commands/
git commit -m "feat: background daemon with Telegram bridge, launchd + systemd services"
```

---

## Phase 5: Packaging & Entry Point

### Task 5.1: Python Entry Point Router

**Files:**
- Modify: `clawed/cli.py`
- Create: `clawed/_typer_app.py`

- [ ] **Step 1: Move existing typer app logic**

Rename the core typer app registration from `cli.py` to `_typer_app.py`. The existing `cli.py` becomes a thin router.

- [ ] **Step 2: Implement the Node.js detection router**

```python
# clawed/cli.py
"""Claw-ED CLI entry point — routes to Ink TUI (Node.js) or Python CLI (fallback)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _find_bundled_cli_js() -> str | None:
    """Find the pre-built cli.js bundled in the package."""
    pkg_dir = Path(__file__).parent
    cli_js = pkg_dir / "_cli_bundle" / "cli.js"
    if cli_js.exists():
        return str(cli_js)
    return None


def _show_node_notice() -> None:
    """One-time notice when Node.js is not installed."""
    notice_file = Path.home() / ".eduagent" / ".node_notice_shown"
    if notice_file.exists():
        return
    print("""
Claw-ED v3.0 — running in classic mode (Python CLI)

For the full experience with the interactive AI assistant,
install Node.js 18+: https://nodejs.org

Classic mode still supports all commands:
  clawed lesson "Topic" -g 8 -s "US History"
  clawed game create "Topic"
  clawed ingest ~/Documents/
""")
    notice_file.parent.mkdir(parents=True, exist_ok=True)
    notice_file.touch()


def main() -> None:
    """Entry point for the `clawed` command."""
    # Allow forcing Python CLI with --python flag
    if "--python" in sys.argv:
        sys.argv.remove("--python")
        _run_python_cli()
        return

    # Try Node.js + bundled CLI
    node = shutil.which("node")
    cli_js = _find_bundled_cli_js()

    if node and cli_js:
        result = subprocess.run([node, cli_js] + sys.argv[1:])
        sys.exit(result.returncode)
    else:
        _show_node_notice()
        _run_python_cli()


def _run_python_cli() -> None:
    """Run the Python typer CLI (fallback mode)."""
    from clawed._typer_app import app
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update pyproject.toml**

```toml
[project]
name = "clawed"
version = "3.0.0"

[project.scripts]
clawed = "clawed.cli:main"
eduagent = "clawed.cli:main"

[tool.setuptools.package-data]
clawed = ["_cli_bundle/*.js", "_cli_bundle/*.js.map"]
```

- [ ] **Step 4: Test both paths**

```bash
# Test Node.js path (should launch Ink TUI)
clawed --version

# Test Python fallback
clawed --python --version

# Test --json still works
clawed --python gen lesson "Test" -g 8 -s "US History" --json
```

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add clawed/cli.py clawed/_typer_app.py pyproject.toml
git commit -m "feat: entry point router — Node.js Ink TUI or Python CLI fallback"
```

---

### Task 5.2: Build Pipeline & Bundle

**Files:**
- Create: `scripts/build.sh`
- Create: `clawed/_cli_bundle/.gitkeep`

- [ ] **Step 1: Create the build script**

```bash
#!/bin/bash
# scripts/build.sh — Build Claw-ED v3: TypeScript CLI + Python wheel
set -euo pipefail

echo "=== Building Claw-ED v3.0 ==="

# Step 1: Build TypeScript CLI
echo "Building TypeScript CLI..."
cd cli
npm install
node scripts/build-cli.mjs
cd ..

# Step 2: Bundle cli.js into Python package
echo "Bundling cli.js into Python package..."
mkdir -p clawed/_cli_bundle
cp cli/source/cli.js clawed/_cli_bundle/cli.js

# Step 3: Build Python wheel
echo "Building Python wheel..."
python3 -m build

echo "=== Build complete ==="
ls -lh dist/*.whl
```

- [ ] **Step 2: Run the build**

```bash
cd ~/Projects/Claw-ED-v0920 && chmod +x scripts/build.sh && bash scripts/build.sh
```
Expected: Produces `dist/clawed-3.0.0-py3-none-any.whl`

- [ ] **Step 3: Verify wheel contents**

```bash
unzip -l dist/clawed-3.0.0-py3-none-any.whl | grep cli_bundle
```
Expected: Shows `clawed/_cli_bundle/cli.js`

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add scripts/build.sh clawed/_cli_bundle/.gitkeep
git commit -m "feat: build pipeline — TypeScript CLI bundled into Python wheel"
```

---

## Phase 6: Polish & Ship

### Task 6.1: Fix PPTX Vocabulary Overcrowding

**Files:**
- Modify: `clawed/export_pptx.py`

- [ ] **Step 1: Find the vocabulary slide generation code in export_pptx.py**

Look for where vocabulary terms are placed on a single slide. Split when count > 4: create multiple vocabulary slides with max 4 terms each.

- [ ] **Step 2: Implement the split logic**

```python
# In the vocabulary slide section of export_pptx.py
MAX_VOCAB_PER_SLIDE = 4
vocab_chunks = [vocabulary[i:i+MAX_VOCAB_PER_SLIDE] for i in range(0, len(vocabulary), MAX_VOCAB_PER_SLIDE)]
for chunk_idx, chunk in enumerate(vocab_chunks):
    slide = prs.slides.add_slide(layout)
    # ... render chunk of terms on this slide
```

- [ ] **Step 3: Run existing PPTX tests**

```bash
cd ~/Projects/Claw-ED-v0920 && python3 -m pytest tests/ -k pptx -v
```

- [ ] **Step 4: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add clawed/export_pptx.py
git commit -m "fix: split vocabulary across multiple slides (max 4 per slide)"
```

---

### Task 6.1b: Fix PPTX Visual Theming

**Files:**
- Modify: `clawed/export_pptx.py`

- [ ] **Step 1: Add topic-based theme selection**

In `export_pptx.py`, add a theme mapping:
```python
TOPIC_THEMES = {
    "exploration": {"bg": "#1a3a5c", "accent": "#c9a96e", "style": "nautical"},
    "renaissance": {"bg": "#4a3728", "accent": "#d4af37", "style": "marble"},
    "revolution": {"bg": "#8b0000", "accent": "#ffd700", "style": "patriotic"},
    # ... more topic-theme mappings
}
```

Apply theme colors to slide backgrounds, title bars, and accent elements based on keyword matching in the lesson topic.

- [ ] **Step 2: Commit**

```bash
git commit -am "feat: topic-based visual theming for PPTX slides"
```

---

### Task 6.1c: Fix Game HTML — Prevention-First Model Selection

**Files:**
- Modify: `clawed/compile_game.py`

- [ ] **Step 1: Enforce code-capable models for game generation**

In `compile_game.py`, before the LLM call, check the model tier. If using Ollama with a non-code model, either:
- Route to a code-capable model (if available)
- Warn the teacher that game quality may be lower
- Fall back gracefully with a simpler game template

- [ ] **Step 2: Commit**

```bash
git commit -am "fix: enforce code-capable models for game HTML generation"
```

---

### Task 6.1d: GitHub Actions CI Pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

```yaml
name: CI
on: [push, pull_request]
jobs:
  python-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.12']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '${{ matrix.python-version }}' }
      - run: pip install -e ".[all]"
      - run: ulimit -n 4096 && python -m pytest tests/ -q --tb=short

  typescript-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v1
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd cli && npm install && node scripts/build-cli.mjs

  wheel-build:
    needs: [python-tests, typescript-build]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/build.sh
      - run: ls -lh dist/*.whl

  publish:
    if: startsWith(github.ref, 'refs/tags/v')
    needs: [wheel-build]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/build.sh
      - run: pip install twine && twine upload dist/*
        env: { TWINE_USERNAME: __token__, TWINE_PASSWORD: '${{ secrets.PYPI_TOKEN }}' }
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions pipeline — tests, build, publish"
```

---

### Task 6.2: Run Full Test Suite & Fix Regressions

- [ ] **Step 1: Run all Python tests**

```bash
cd ~/Projects/Claw-ED-v0920 && ulimit -n 4096 && python3 -m pytest tests/ -q --tb=short
```
Expected: All 1609+ tests pass

- [ ] **Step 2: Run TypeScript build**

```bash
cd ~/Projects/Claw-ED-v0920/cli && node scripts/build-cli.mjs
```
Expected: Build succeeds

- [ ] **Step 3: Verify no "Claude" in user-facing output**

```bash
cd ~/Projects/Claw-ED-v0920/cli && grep -r "Claude Code" source/src/ --include="*.ts" --include="*.tsx" -l
```
Expected: No hits in user-facing strings (SDK imports are fine)

- [ ] **Step 4: Fix any regressions found**

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git commit -am "fix: address test regressions from v3 integration"
```

---

### Task 6.3: Rewrite README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite README for v3**

Structure:
1. Logo (ASCII)
2. One-line description: "Your AI co-teacher — generate lessons, games, slides, and assessments from your terminal."
3. Install: `pip install clawed`
4. Quick start: `clawed` (NL mode) or `clawed lesson "Topic" -g 8 -s "US History"`
5. Features list (16 features, brief)
6. Telegram: `clawed daemon start`
7. Providers supported (Anthropic, OpenAI, Google, Ollama)
8. For teachers: cost breakdown, demo mode
9. Community links (GitHub, PyPI, landing page, game gallery)
10. License: MIT

- [ ] **Step 2: Update CHANGELOG.md**

Add v3.0.0 entry at top with all major changes.

- [ ] **Step 3: Commit**

```bash
cd ~/Projects/Claw-ED-v0920
git add README.md CHANGELOG.md
git commit -m "docs: rewrite README and CHANGELOG for v3.0.0"
```

---

### Task 6.4: Ship to PyPI and GitHub

- [ ] **Step 1: Build the final wheel**

```bash
cd ~/Projects/Claw-ED-v0920 && bash scripts/build.sh
```

- [ ] **Step 2: Upload to PyPI**

```bash
cd ~/Projects/Claw-ED-v0920 && twine upload dist/clawed-3.0.0*
```

- [ ] **Step 3: Create GitHub release**

```bash
cd ~/Projects/Claw-ED-v0920
git tag v3.0.0
git push origin main --tags
gh release create v3.0.0 --title "Claw-ED v3.0.0 — The Agentic Layer for Education" --notes-file CHANGELOG.md
```

- [ ] **Step 4: Push to all fleet nodes**

```bash
ssh crusty "pip install --upgrade clawed"
ssh sirhan "pip install --upgrade clawed"
ssh manfred "pip install --upgrade clawed"
ssh amber "pip install --upgrade clawed"
```

- [ ] **Step 5: Update landing page**

Update `docs/index.html` at `sirhanmacx.github.io/Claw-ED` with v3 branding.

- [ ] **Step 6: Final verification**

```bash
pip install clawed
clawed --version  # Should show 3.0.0 (Claw-ED)
clawed  # Should launch Ink TUI with animated logo
```

---

## Execution Order & Dependencies

```
Phase 0 (JSON Bridge) ─────► MUST complete first
  │
  ├── Phase 1 (Branding) ──► can start in parallel with Phase 0
  │     │
  │     ├── Phase 2 (Tools) ──► needs Phase 0 + Phase 1
  │     │
  │     └── Phase 3 (LLM Router) ──► needs Phase 1 only (independent of Phase 2)
  │           │
  │           └── Phase 4 (Daemon) ──► needs Phase 2 + Phase 3
  │
  └── Phase 5 (Packaging) ──► needs Phase 1 + Phase 2
        │
        └── Phase 6 (Polish & Ship) ──► needs ALL phases
```

**Parallelism opportunities:**
- Phase 0 + Phase 1 run in parallel
- Phase 2 + Phase 3 run in parallel (both need Phase 1, Phase 2 also needs Phase 0)
- Phase 4 waits for both Phase 2 + Phase 3
- Phase 5 can start as soon as Phase 1 + Phase 2 are done
- Phase 6 is the final gate requiring everything
