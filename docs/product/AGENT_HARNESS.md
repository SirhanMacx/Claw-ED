# Claw-ED Agent Harness

Claw-ED is an open-source harness for running an AI agent on a teacher's Mac.
The agent is general purpose enough to read files, run approved tools, organize
work, and create artifacts, but it ships with prebuilt skills for education:
lesson bundles, assessments, handouts, slides, differentiation, review games,
curriculum search, standards alignment, and teacher-style learning.

The simplest description:

> Claw-ED is a local AI-agent harness for teachers. Bring your own model key,
> teach it your materials, and it gives the agent safe tools for classroom work.

## What "Harness" Means

The harness includes:

- A local Mac app or local web UI.
- A local Python agent process on `127.0.0.1`.
- A tool registry of teacher-assistant skills and general Mac actions.
- A permission system for file writes, shell commands, network calls, package
  installs, and publishing actions.
- A workspace under `~/.eduagent/`.
- Provider setup for OpenRouter, Ollama, Anthropic, OpenAI, and Google.

The harness is not a hosted lesson website. It is the control surface around an
agent running for one teacher on one machine.

## Local Agent, Provider Boundary

The agent process itself is local. Your app window talks to it over loopback.
Your files and generated artifacts stay on your Mac by default.

Model calls are different:

- If you use local Ollama at `http://localhost:11434`, model prompts stay on
  your machine.
- If you use OpenRouter, Ollama Cloud, Anthropic, OpenAI, Google, or another
  cloud provider, Claw-ED sends the prompt and relevant context to that provider
  so the model can answer.
- That provider may process, log, retain, or route data according to its own
  terms, privacy policy, and model-provider chain.
- District pilots should choose the provider first, then configure Claw-ED to
  use only that provider or an approved router/model allowlist.

This is the honest privacy claim: local harness, local files by default, cloud
model data sharing only when the teacher or district chooses a cloud model.

## Recommended Provider Paths

### OpenRouter

Best for most teachers who want one key and many model choices.

1. Go to `https://openrouter.ai/keys`.
2. Sign in.
3. Create an API key. Give it a name such as `Claw-ED`.
4. Optional but recommended: set a credit limit.
5. Copy the key once.
6. Save it on the Mac:

```bash
clawed config set-key openrouter YOUR_KEY
clawed config set-model openrouter --model minimax/minimax-m3
```

OpenRouter is a cloud router. The prompt/context is sent to OpenRouter and may
also be sent to the downstream model provider OpenRouter uses for the selected
model.

### Ollama Local

Best for privacy-sensitive or technical users who are comfortable installing
and managing local models.

1. Install Ollama for macOS from `https://ollama.com/download/mac`.
2. Pull a model:

```bash
ollama pull llama3.2
```

3. Configure Claw-ED:

```bash
clawed config set-model ollama --model llama3.2
```

Local Ollama serves on `http://localhost:11434` by default. Prompts stay on the
Mac, but quality and speed depend on the Mac and model.

### Ollama Cloud

Best for teachers who want Ollama's simpler model experience but do not want to
run local models.

1. Create an Ollama account.
2. Create an API key in Ollama settings.
3. Save it:

```bash
clawed config set-key ollama YOUR_KEY
clawed config set-model ollama --model gemma4:31b-cloud
```

Ollama Cloud is not local. Prompts/context are sent to Ollama's cloud service.

## Where Keys Are Stored

Claw-ED looks for keys in this order:

1. Environment variables such as `OPENROUTER_API_KEY` or `OLLAMA_API_KEY`.
2. Existing Claude Code OAuth credentials for the Anthropic provider.
3. The OS keychain when available.
4. `~/.eduagent/secrets.json` with user-only file permissions.

Use `clawed config set-key PROVIDER YOUR_KEY` for the normal path. It tries the
keychain first and falls back to `~/.eduagent/secrets.json`.

Supported provider names:

- `openrouter`
- `ollama`
- `anthropic`
- `openai`
- `google`

## How Skills Work

The model does not directly edit your Mac. It asks the harness to call tools.
Each tool has:

- a name;
- a description the model sees;
- a schema for allowed parameters;
- a risk level;
- an approval rule.

Examples:

- `search_my_materials`: search ingested teacher files.
- `generate_lesson_bundle`: create teacher DOCX, student DOCX, slides, and
  supporting materials.
- `write_file`: write a local file after approval.
- `run_command`: run a shell command after explicit approval.
- `switch_model`: change provider/model.

The Skills view in the Mac app reads the live tool registry from
`/api/agent/tools`, so it shows what the agent can actually do on that machine.

## Permissions

Claw-ED tools use risk levels:

- `read_only`: allowed without approval.
- `write_local`: asks before writing local files unless the teacher opts into
  auto-approve.
- `network_call`: asks before using external services unless the teacher opts
  into auto-approve.
- `command_exec`: always asks. "Always allow" is scoped to the exact command.
- `package_install`: always asks.
- `external_publish`: always asks.

The important rule: words are not actions. If a tool did not run and return
success, the action did not happen.

## `/goal` And `/loop` Product Direction

Claw-ED should add two first-class agent skills:

- `/goal`: define the active outcome, constraints, done conditions, and
  verification evidence. The agent should write a local `GOAL.md`, update status
  as work progresses, and include the goal in future context.
- `/loop`: create a bounded work loop tied to a goal, such as "check health every
  30 minutes and restart if down" or "each morning, prepare tomorrow's warm-up."
  Loops must be visible, pausable, and permission-scoped. They must not bypass
  approvals for shell commands, package installs, or external publishing.

Both should be education-first but general-purpose: teachers can use them for
weekly planning, grading queues, standards coverage audits, and classroom
material preparation.
