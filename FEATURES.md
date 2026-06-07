# Agent Capabilities

Claw-ED is a personal AI teaching agent. These are the things it can do.

---

## Curriculum Knowledge Base

Feed the agent your lesson plans, handouts, unit plans, and slides. It chunks every document into searchable sections and stores them in a local semantic database. When you ask for anything, it searches your materials first -- grounding every generation in your own prior work.

Powered by Ollama embeddings (mxbai-embed-large) with TF-IDF fallback for offline use.

---

## Voice Learning

The agent reads your files and extracts your teaching fingerprint -- style, tone, vocabulary, structure, assessment preferences. Generated content sounds like you wrote it, not like a generic AI template.

---

## Generation -- in your voice

- Unit plans with essential questions and daily lesson sequences
- Daily lessons (AIM, Do Now, instruction, guided practice, exit ticket)
- Worksheets, quizzes, rubrics, and DBQ prompts
- IEP/504 accommodations and differentiation (struggling, advanced, ELL)
- Substitute teacher packets and parent communications
- Professional PPTX slides with section dividers
- Polished DOCX with headers, footers, and IEP/ELL callout boxes

---

## Standards Alignment -- 50 states

- CCSS, NGSS, C3, and state-specific frameworks
- Curriculum gap analyzer -- find what you have not covered yet
- Standards search by subject and grade

---

## Autonomous Behavior

The agent does not just respond to commands. It takes initiative:

- **Search-first:** Searches your curriculum files before every generation
- **Status narration:** "Searching your files... Found 3 related lessons. Generating now..."
- **Proactive suggestions:** "I made your lesson. Want me to create a matching worksheet?"
- **Scheduled tasks:** Morning prep, weekly planning, feedback digests -- configurable in HEARTBEAT.md
- **Multi-step planning:** Complex requests like "prepare my week" trigger a step-by-step execution plan
- **Autonomy progression:** After consistent approvals, the agent offers to auto-approve routine actions

---

## Interfaces

| Method | How to use it |
|--------|--------------|
| **No-terminal web app** | `clawed app` — opens a warm, Claude-style local web app in your browser, with guided API-key setup |
| **Mac menu-bar app** | `mac-app/` — one-click start/stop, health dot, and a QR code to open Claw-ED on your phone over the LAN |
| **Terminal chat** | `clawed` or `clawed chat` |
| **Web dashboard** | `clawed serve` (the same web app, without auto-opening a browser) |
| **Telegram bot** | `clawed bot --token TOKEN` |
| **Full-screen TUI** | `pip install 'clawed[tui]'` then `clawed tui` |
| **Student bot** | Students join with class codes, ask questions in your voice |
| **MCP server** | Expose tools to any AI agent |

### Ask your co-teacher (live)

From the web app's **Create** screen, type a request in plain English — a hook, a
Do Now, three discussion questions, an IEP scaffold — and the answer streams in
token-by-token, rendered as Markdown, with one-click **Copy** and **Download .md**.
Quick-start chips prefill common asks. It runs on whichever provider you've
configured, including OpenRouter (e.g. `minimax/minimax-m3`) or a fully local model.

### Create any artifact

The same Create screen builds full artifacts from a pickable card — **full unit**,
**single lesson**, **materials only**, **quiz / assessment**, **differentiated
version**, or **review game** — and shows lessons in an inline preview before you
download.

### Bring your own model

Choose **Anthropic**, **OpenAI**, **Google (Gemini)**, or **OpenRouter** (any model
it routes to), each with in-app onboarding that walks you through getting a key —
or run a fully local **Ollama** model offline. Keys are stored only on your machine.

---

## 3-Layer Cognitive Memory

| Layer | What it stores | How it works |
|-------|---------------|-------------|
| **Identity** | Teaching style, subject, grades, voice | Persona extraction from your files |
| **Curriculum** | Current unit, pacing state, coverage | SQLite projections |
| **Episodic** | Past interactions, semantic recall | Embedding model (Ollama / TF-IDF) |

Memory improves over time. Ratings, edits, and approvals all feed back into future generations.

---

## Safety Guardrails

- Approval gates for consequential actions (publishing, sharing with students)
- Student-facing output always requires teacher review
- Closed feedback loop: ratings improve future generation
- Custom teacher tools via YAML -- no code needed, full agent integration

---

## Privacy

- Your files never leave your machine (unless you choose a cloud LLM)
- Curriculum knowledge base is local SQLite -- never uploaded
- API keys stored in OS keychain
- No telemetry, no tracking, no data collection
- Works fully offline with local Ollama
