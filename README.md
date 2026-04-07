# Claw-ED

An open-source CLI agent that generates lesson plans, assessments, slideshows, and games in a teacher's own voice. Feed it your files, talk to it in the terminal or on Telegram.

<p align="center">
  <a href="https://pypi.org/project/clawed/"><img src="https://img.shields.io/pypi/v/clawed?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/clawed/"><img src="https://img.shields.io/pypi/pyversions/clawed" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="MIT"></a>
  <a href="https://pepy.tech/project/clawed"><img src="https://static.pepy.tech/badge/clawed" alt="Downloads"></a>
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

- CLI agent with 47+ tools (lesson gen, assessments, games, simulations, animations, differentiation)
- **Uses your own images** — extracts maps, cartoons, diagrams from your PPTX files and puts them in generated slides
- Animated educational videos (timelines, concept maps, cause-effect diagrams) via [Manim](https://www.manim.community/)
- Ingests PDF, DOCX, PPTX, TXT, MD — extracts teaching style, images, and curriculum structure
- Semantic search over your curriculum (ONNX MiniLM embeddings, FTS5, embedding-based image matching)
- [Karpathy-style wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — compiles your files into organized markdown articles
- [Self-distillation](https://arxiv.org/abs/2604.01193) — learns from your ratings and edits, updates its own soul.md
- Web search (DuckDuckGo + Playwright), Google Drive integration
- 50-state standards alignment (NY Regents, TX STAAR, CA CAASPP, etc.)
- Telegram bot with file delivery, interactive `/models` selector, shared session memory
- Works with Ollama, Anthropic, OpenAI, Google, OpenRouter — interactive model switching
- Scheduled tasks (morning prep, gap detection, wiki maintenance)
- Self-equipping — can install Python packages (--user scope) and create YAML tool templates when it needs a capability it doesn't have
- DOCX, PPTX, PDF, HTML, MP4 export
- MCP server for Claude Code / VS Code integration
- MIT licensed, no telemetry, no accounts

### Trust model

Claw-ED is a **local-first tool** designed for a teacher's own machine. It reads your files, calls LLM APIs you configure, and writes to `~/.eduagent/`. The web API (if you run `clawed serve`) requires a bearer token and binds to localhost by default. Self-equipping installs packages in `--user` scope only. The Telegram bot runs as a background process on your machine. Nothing is sent anywhere except the LLM provider you choose.

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

**Recommended:** [Ollama Pro](https://ollama.com/pro) ($20/mo) — unlimited access to good models, easiest setup. For best output quality, use an Anthropic or OpenAI API key (pay per use). OpenRouter lets you pick from any model. Google Gemini has a free tier. Local Ollama runs fully offline for free.

---

## Dev setup

```bash
git clone https://github.com/SirhanMacx/Claw-ED.git
cd Claw-ED
pip install -e ".[dev]"
pytest tests/
```

PRs welcome. Built by a teacher in New York. If you're a teacher, a developer, or just curious — jump in.

- [Issues](https://github.com/SirhanMacx/Claw-ED/issues)
- [Discussions](https://github.com/SirhanMacx/Claw-ED/discussions)

---

MIT License
