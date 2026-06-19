# Claw-ED

> Made by a teacher, for teachers.

An open-source CLI agent that generates complete lesson bundles — plans, handouts, slides, differentiated versions, games, and more — in your teaching voice. Feed it your files. It learns how you teach. Then it does the work for you.

**Sibling project:** [Claw-STU](https://sirhanmacx.github.io/Claw-STU/) — the student-facing personal learning agent. Ed builds the lessons; Stuart helps students understand them.

Claw-ED is maintained as part of [MacxLabs](https://macxlabs.app/?src=github-claw-ed-readme). Teaching AP or Regents? We also build [Review Arcade Teacher HQ](https://macxlabs.app/teacherhq/?src=github-claw-ed-readme) — ready-to-run review-week sprints, made by a fellow teacher. If Claw-ED saves you prep time, you can also [support the project](https://macxlabs.app/support/?src=github-claw-ed-readme).

<p align="center">
  <img src="https://img.shields.io/badge/version-v6.19.2026.4-blue" alt="Version">
  <a href="https://pypi.org/project/clawed/"><img src="https://img.shields.io/pypi/v/clawed?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/clawed/"><img src="https://img.shields.io/pypi/pyversions/clawed" alt="Python"></a>
  <a href="https://github.com/SirhanMacx/Claw-ED/actions/workflows/ci.yml"><img src="https://github.com/SirhanMacx/Claw-ED/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="MIT"></a>
  <a href="https://pepy.tech/project/clawed"><img src="https://static.pepy.tech/badge/clawed" alt="Downloads"></a>
  <a href="https://github.com/SirhanMacx/Claw-ED/stargazers"><img src="https://img.shields.io/github/stars/SirhanMacx/Claw-ED?style=social" alt="Stars"></a>
</p>

```bash
pip install clawed
clawed
```

---

## What it does

You point it at a folder of your old lessons. It reads them, figures out how you teach, and generates new ones that match your style. Teacher DOCX, student DOCX, slides PPTX — all at once.

```
$ clawed

  🍎 Hey Mr. Maccarello! What are we working on today?

❯ Make me a lesson on the causes of the French Revolution for 10th grade

  Searching your materials...
  Found 3 docs on this topic.
  Generating lesson package...

  ✓ French_Revolution_teacher.docx
  ✓ French_Revolution_student.docx
  ✓ French_Revolution_slides.pptx
```

It also runs as a Telegram bot. Same brain, same files, same memory. Ask it to make something from your phone and the files show up in chat.

---

## Features

- **51 agent tools** — lesson gen, assessments, games, simulations, animations, curriculum maps, differentiation, project arcs, and more
- **Quality gate with auto-retry** — 12 pedagogical checks (Bloom's progression, stimulus-based assessment, differentiation specificity, diversity audit) validate every lesson before delivery. Failures auto-retry with specific feedback.
- **Uses your own images** — extracts maps, cartoons, diagrams from your PPTX files and puts them in generated slides (58K+ images from real curriculum). Vision model filters for quality.
- **Writes like you** — AI-ism removal strips "delve", "utilize", "leverage" and 70+ other LLM tells so output reads like a teacher wrote it
- **Structured jigsaws + creative activities** — generates timed rotation schedules, graphic organizers, role plays, debates, podcast scripts, gallery walks, mock trials
- **Multi-day project arcs** — 5-day projects with choice boards, curated research databases, rubrics, debate prep sheets, and culminating performances (gallery walks, Philosophical Chairs)
- **Export everywhere** — Teacher DOCX, Student DOCX, PPTX slides, Anki flashcards, Kahoot quizzes, Common Cartridge (.imscc for Canvas/Moodle), audio narration scripts, study guides
- Interactive curriculum map — visualize how your topics, standards, and vocabulary connect
- Animated educational videos (timelines, concept maps, cause-effect diagrams) via [Manim](https://www.manim.community/)
- Ingests PDF, DOCX, PPTX, TXT, MD — extracts teaching style, images, and curriculum structure
- Semantic search over your curriculum (ONNX MiniLM embeddings, FTS5, embedding-based image matching)
- [Karpathy-style wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — compiles your files into organized markdown articles
- [Self-distillation](https://arxiv.org/abs/2604.01193) — learns from your ratings and edits, updates its own soul.md
- Web search (DuckDuckGo + Playwright), Google Drive integration, Google Classroom posting
- 50-state standards alignment (NY Regents, TX STAAR, CA CAASPP, etc.)
- Telegram bot with file delivery, interactive `/models` selector, shared session memory
- **Autonomous scheduling** — morning prep auto-generates lessons at 6am, weekly planning drafts next week every Sunday, gap detection scans standards coverage, self-distillation improves output quality
- **Chrome extension** — highlight text on any webpage, right-click, generate a lesson using that text as a primary source
- **Real-time classroom mode** — WebSocket-based live sessions with slide control, timers, and polls. Students connect via class code.
- **Exit ticket auto-grading** — keyword analysis + formative feedback with sentence starter suggestions
- **Classroom memory** — persistent profile (student count, ELL/IEP needs, tech available) injected into every generation
- **Adaptive feedback loop** — exit ticket results feed into next lesson (reteach/extend recommendations + parent notifications)
- Works with Ollama, Anthropic, OpenAI, Google, OpenRouter — interactive model switching
- **Central approval policy** — every tool classified by risk level (read_only/write_local/network_call/package_install). Sensitive actions require teacher confirmation.
- DOCX, PPTX, PDF, HTML, MP4, TSV, CSV, IMSCC, TXT export
- MCP server for Claude Code / VS Code integration
- MIT licensed, no telemetry, no accounts

### What makes this different

Other AI tools generate one thing at a time. Claw-ED generates **everything at once** — lesson plan, handout, slides, differentiated versions, a review game, a learning journey, flashcards, a Kahoot quiz, and a research report. One request, 9+ files, in your voice.

Other tools don't know how you teach. Claw-ED **reads your actual files** — your old lessons, your PPTX slides, your assessments — and learns your vocabulary, scaffolding patterns, and teaching style. The output sounds like you wrote it.

Other tools run in the cloud. Claw-ED runs **on your machine**. Your files, your students, your lessons — none of it leaves your computer.

Other tools give you a first draft you have to edit. Claw-ED has a **12-check quality gate** that catches summaries instead of real sources, generic differentiation, missing checks for understanding, and Bloom's Level 1 exit tickets. Bad output gets rejected and regenerated automatically — teachers get print-ready lessons.

### Trust model

Claw-ED is a **local-first tool** designed for a teacher's own machine. It reads your files, calls LLM APIs you configure, and writes to `~/.eduagent/`. The web API (if you run `clawed serve`) requires a bearer token and binds to localhost by default. Self-equipping installs packages in `--user` scope only. The Telegram bot runs as a background process on your machine. Nothing is sent anywhere except the LLM provider you choose.

### Feature Maturity

| Tier | Features |
|------|----------|
| **Stable** | Lesson / unit / assessment generation, multi-format export (DOCX, PPTX, PDF, Markdown, IMSCC), provider & model setup, voice & style learning, quality gate pipeline |
| **Beta** | Telegram bot, Chrome extension, classroom mode, community sharing, scheduler automation |
| **Experimental** | Features that still rely on in-memory state without persistent backing (e.g., live classroom sessions, saved sources, community lesson store). These work within a single process lifetime but do not yet survive restarts. |

---

## Commands

```bash
clawed                                    # chat with Ed
clawed ingest ~/Documents/Lessons/        # teach it your style
clawed lesson "Topic" -g 8 -s "US History"  # daily lesson
clawed unit "Topic" -g 9 -w 3            # 3-week unit
clawed assess "Topic" --type crq          # CRQ, DBQ, quiz, rubric
clawed game create "Topic" -g 8           # HTML learning game
clawed simulate create "Topic"            # interactive simulation
clawed differentiate -l lesson.json       # IEP/504/ELL mods
clawed kb compile                         # compile curriculum wiki
clawed kb query "question"                # search your wiki
clawed kb lint                            # wiki health check
clawed bot                                # start Telegram bot
clawed drive auth                         # connect Google Drive
clawed schedule list                      # scheduled tasks
clawed setup                              # re-run setup
clawed mcp-server                         # MCP for Claude Code
```

---

## How the voice learning works

It reads your files and extracts patterns:
- Lesson structure (I Do / We Do / You Do, stations, seminars)
- Assessment format (CRQ, DBQ, exit ticket style, Do Now format)
- Writing frameworks (TEA, RACE, CER)
- Scaffolding (sentence starters, graphic organizers, word banks)
- Source preferences, grouping strategies, classroom personality

Stored in `~/.eduagent/workspace/soul.md`. You can read it, edit it, or let it evolve.

---

## Setup

```bash
pip install clawed
clawed
```

It walks you through picking a provider and an API key.

**Recommended:** [Ollama Pro](https://ollama.com/pricing) ($20/mo) — unlimited access to good models, easiest setup. For best output quality, use an Anthropic or OpenAI API key (pay per use). OpenRouter lets you pick from any model. Google Gemini has a free tier. Local Ollama runs fully offline for free.

---

## Dev setup

```bash
git clone https://github.com/SirhanMacx/Claw-ED.git
cd Claw-ED
pip install -e ".[dev]"
pytest tests/
```

PRs welcome. Built by a teacher in New York. If you're a teacher, a developer, or just curious — jump in.

- [Getting Started](docs/GETTING_STARTED.md) — 5-minute setup guide
- [FAQ](docs/FAQ.md) — common questions
- [Issues](https://github.com/SirhanMacx/Claw-ED/issues)
- [Discussions](https://github.com/SirhanMacx/Claw-ED/discussions)
- [Security](SECURITY.md) — privacy and data handling

---

MIT License
