# Claw-ED Public Positioning And Ad Copy

## Core Position

Claw-ED is an open-source AI-agent harness for teachers.

It runs a local agent on a teacher's Mac, connects to the model provider the
teacher or district chooses, and gives that agent education-ready skills:
curriculum search, lesson bundles, slides, handouts, differentiation, review
games, standards alignment, file organization, and approved Mac actions.

## One-Liners

- Your own AI teaching agent, running from your Mac.
- A local AI-agent harness with prebuilt teacher-assistant skills.
- Bring your own model key. Keep the harness local. Teach it your materials.
- OpenRouter for easy hosted models. Local Ollama for technical privacy-first
  users.
- Not a chatbot tab. A permissioned agent that can make the files.

## Hero Copy

Headline:

Claw-ED is an AI-agent harness for teachers.

Subhead:

Run a local agent on your Mac, connect your own model key, and give it safe
education skills for lessons, slides, handouts, differentiation, review games,
curriculum search, and classroom workflow.

CTA:

- Mac download coming soon
- View source on GitHub
- Read the setup guide

Trust line:

The harness and workspace run locally. If you choose a cloud model provider like
OpenRouter or Ollama Cloud, prompt/context is sent to that provider. Local
Ollama can keep model calls on your Mac.

## Teacher Version

You already have the materials. Claw-ED gives you a local AI agent that can use
them.

Point it at your lesson folders. Ask for tomorrow's Do Now, a full lesson
bundle, a sub packet, a differentiated handout, a review game, or help cleaning
up files. It works like a co-teacher with tools, not a blank chatbot.

You choose the model. OpenRouter is easiest for most people. Ollama can run
locally if you are more technical and want tighter privacy or lower recurring
cost.

## District/Admin Version

Claw-ED is a local-first AI-agent harness for managed teacher Macs.

The Mac app talks to a local agent over loopback. Generated work stays on the
teacher's Mac by default. Risky actions are permissioned. The model provider is
bring-your-own: districts can approve OpenRouter, Ollama Cloud, Anthropic,
OpenAI, Google, or local Ollama depending on policy.

This is a practical reason to pilot managed Mac minis for teachers: one stable
device, one local agent, one workspace, normal Apple deployment controls, and a
clear provider boundary.

## Privacy Copy

Short:

Claw-ED's agent and workspace run locally. Cloud model calls still send
prompt/context to the provider you choose.

Medium:

The Mac app talks to a local agent on `127.0.0.1`, and generated files stay on
your Mac by default. If you use OpenRouter, Ollama Cloud, Anthropic, OpenAI,
Google, or another cloud provider, Claw-ED sends the prompt and relevant context
to that provider. If you use local Ollama, model calls can stay on your machine.

Do not say:

- "Nothing ever leaves your computer."
- "Fully private" without naming local Ollama.
- "No data is shared" when a cloud provider is configured.

## API Key Copy

An API key is how Claw-ED pays or authenticates with the model provider you pick.
Claw-ED does not sell you a hidden model subscription. You bring the key, choose
the provider, and can switch later.

Recommended setup:

1. Create an OpenRouter key at `https://openrouter.ai/keys`.
2. Run:

```bash
clawed config set-key openrouter YOUR_KEY
clawed config set-model openrouter --model minimax/minimax-m3
```

Local setup:

```bash
ollama pull llama3.2
clawed config set-model ollama --model llama3.2
```

Keys are checked from environment variables first, then the OS keychain, then
`~/.eduagent/secrets.json`.

## Skills Copy

Skills are the agent's toolbelt.

The model can ask to use a skill, but the harness decides whether it is allowed.
Read-only skills run directly. File writes, network calls, package installs,
publishing, and shell commands go through permission rules. `run_command` always
asks before it touches the Mac.

Teacher-ready skills include:

- search my materials;
- learn my style;
- generate a lesson bundle;
- build assessments and rubrics;
- create differentiated supports;
- make review games and simulations;
- export documents and slides;
- organize workspace files;
- switch model/provider.

## `/goal` And `/loop` Copy

Coming direction:

- `/goal`: set the outcome, constraints, done conditions, and evidence.
- `/loop`: run a bounded, visible, pausable agent loop tied to that goal.

Examples:

- `/goal Build tomorrow's Global 9 Renaissance lesson from my existing unit.`
- `/loop Every weekday at 6am, draft tomorrow's Do Now and save it to Workspace.`

Every loop must be visible and permission-scoped. No loop should bypass approval
for shell commands, package installs, or publishing.

## Short Ads

Teacher social:

I built the AI tool I wanted as a teacher: a local agent on your Mac that can
use your lesson folders, make the files, and ask before it does risky stuff.
Bring your own OpenRouter key or run local Ollama. Free and open source.

District social:

The case for teacher Mac minis: one managed classroom hub running a local
AI-agent harness. Claw-ED is free, open source, bring-your-own-provider, and
built around permissions instead of blind automation.

Search ad:

Open-source AI teaching agent for Mac. Bring your own API key. Local harness,
teacher skills, permissioned file and command tools.

Download page card:

Free Mac app. Open-source harness. OpenRouter, Ollama, Anthropic, OpenAI,
Google. Your model, your Mac, your teaching workflow. Mac download coming soon.

## Required Links

- Public page: `https://macxlabs.app/clawed/`
- Mac download: coming soon; do not publish a DMG link until the Mac prototype
  and companion iOS path have been tested.
- Source: `https://github.com/SirhanMacx/Claw-ED`
- OpenRouter keys: `https://openrouter.ai/keys`
- Ollama macOS: `https://ollama.com/download/mac`
- Ollama local API docs: `https://docs.ollama.com/api/introduction`
- Trust docs: `docs/product/TRUST_AND_SECURITY.md`
