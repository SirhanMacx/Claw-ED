# Claw-ED FAQ

Frequently asked questions from teachers using Claw-ED.

---

## Does it work offline?

Yes. If you use a local LLM through Ollama, Claw-ED runs entirely on your machine with no internet connection required. Install Ollama, pull a model (e.g. `ollama pull gemma3`), set your provider to `ollama` in settings, and everything -- ingestion, lesson generation, slides, handouts, games -- works offline.

Cloud providers (Anthropic, OpenAI, Google, OpenRouter) require internet access to reach their APIs, but all your files and data still stay local.

---

## Is my data private?

Yes. Claw-ED is local-first by design:

- All generated files (DOCX, PPTX, HTML) are saved to `~/clawed_output/` on your machine.
- Your curriculum knowledge base lives in a local SQLite database at `~/.eduagent/memory/`.
- API keys are stored with owner-only file permissions (`0600`).
- Nothing is uploaded to Claw-ED servers -- there are no Claw-ED servers.
- The only external network calls go to the LLM provider you choose, and only the prompt text is sent.

For full details, see [SECURITY.md](../SECURITY.md).

---

## How much does it cost?

Claw-ED itself is free and open-source. The only cost is the LLM provider you choose:

| Provider | Cost | Notes |
|----------|------|-------|
| **Ollama** (local) | Hardware only | Runs on your own machine. A capable laptop or desktop with 16 GB+ RAM works well. Electricity cost is roughly $5-20/month depending on usage. |
| **Anthropic** (Claude) | Pay-per-use | Highest quality output. A typical lesson bundle costs $0.02-0.10 in API usage. |
| **OpenAI** (GPT-4o) | Pay-per-use | Similar pricing to Anthropic. Free tier available with rate limits. |
| **Google** (Gemini) | Free tier available | Generous free tier for moderate usage. Pay-per-use beyond that. |
| **OpenRouter** | Pay-per-use | Access to many models through one API key. Pricing varies by model. |

Most teachers generating a few lessons per day spend under $5/month on cloud APIs.

---

## Can I edit the output?

Yes. Every file Claw-ED generates is a standard, editable format:

- **Lesson plans** and **student handouts** are `.docx` files -- open them in Word, Google Docs, or LibreOffice.
- **Slideshows** are `.pptx` files -- open them in PowerPoint, Google Slides, or Keynote.
- **Review games** and **learning journeys** are `.html` files -- open them in any browser, or edit the source in any text editor.
- **Research reports** are `.md` (Markdown) files.

Nothing is locked or proprietary. Edit, remix, and share freely.

---

## What file formats does it read?

Claw-ED can ingest the following formats from your existing teaching materials:

| Format | Extension |
|--------|-----------|
| PDF | `.pdf` |
| Word documents | `.docx`, `.doc` |
| PowerPoint presentations | `.pptx`, `.ppt` |
| Plain text | `.txt` |
| Markdown | `.md` |
| HTML | `.html` |
| Excel spreadsheets | `.xlsx` |

Upload your existing lesson plans, handouts, slideshows, and curriculum docs. Claw-ED extracts your teaching voice, vocabulary, and content patterns to generate materials that sound like you.

---

## How long does lesson generation take?

A full lesson bundle (lesson plan + student handout + slideshow + differentiation packets + review game + learning journey) typically takes **2-4 minutes** depending on:

- **LLM provider speed**: Cloud APIs (Anthropic, OpenAI) are generally faster than local Ollama models.
- **Model size**: Larger models produce higher quality but take longer.
- **Image generation**: If slide images are enabled, image fetching adds 15-30 seconds.
- **Network latency**: Only relevant for cloud providers.

Individual outputs (just a lesson plan, just a game) take under a minute.

---

## Does it work with my state standards?

Yes. Claw-ED has **50-state standards** built in. When you set your state in your teacher profile, every generated lesson automatically aligns to your state's standards for the relevant subject and grade level.

Standards are embedded directly into the lesson plan, student handout, and slideshow -- no manual lookup required.

---

## Can I use it on my phone?

Yes. Claw-ED includes a Telegram bot that gives you full access from any device:

1. Set up the Telegram bot (see [BOT_SETUP.md](BOT_SETUP.md)).
2. Send messages like "Make a lesson on the water cycle for 5th grade science."
3. Ed generates everything and sends the files right to the chat.

The bot supports all the same features as the CLI and web dashboard: lesson generation, curriculum search, feedback, student chat, and more.

---

## What models work best?

Recommended models ranked by output quality:

| Model | Provider | Quality | Speed | Best For |
|-------|----------|---------|-------|----------|
| **Claude** (claude-sonnet-4-6) | Anthropic | Highest | Fast | Best overall lesson quality, nuanced differentiation |
| **GLM 5.1** | Local/API | Excellent | Medium | Strong all-around, good for schools wanting local control |
| **Gemma 4** | Ollama (local) | Very Good | Medium | Best fully-local option, no API key needed |
| **GPT-4o** | OpenAI | Very Good | Fast | Reliable, widely available |
| **Llama 3.2** | Ollama (local) | Good | Fast | Fastest local option, lighter hardware requirements |

For the best experience, start with Claude or GPT-4o. Switch to a local model (Gemma 4 or Llama 3.2) once you are comfortable and want to eliminate API costs.

---

## Can multiple teachers share one installation?

Yes. Each teacher gets their own `teacher_id` that keeps their persona, curriculum knowledge base, feedback history, and generated content separate. Multiple teachers can use the same Claw-ED installation on a shared server or school machine.

For school-wide deployments, Claw-ED also supports:

- **School setup** with shared curriculum libraries.
- **Department-level content sharing** so teachers can browse and rate each other's best lessons.
- **Per-teacher analytics** to track generation quality over time.

See the `/api/school/` endpoints in [API.md](API.md) for details.

---

## What if the lesson isn't good enough?

Rate it. Claw-ED has a built-in feedback loop:

1. **Rate the lesson** (1-5 stars) through the bot, CLI, or web dashboard.
2. **Add notes** about what to improve ("the primary source was too easy", "vocabulary list was too long").
3. **Ed learns**: Feedback is analyzed and used to improve future generations. High-rated lessons (4-5 stars) are added to your teaching corpus so Ed learns your preferences.
4. **Trigger improvement**: Run the improvement cycle to refine Ed's prompts based on accumulated feedback.

Over time, lessons get closer to your style and standards. The more feedback you give, the better Ed gets.

---

## Does it support special education?

Yes. Every lesson bundle automatically generates differentiation packets for:

- **IEP/504 Accommodations** -- specific, actionable modifications for students with individualized education programs or 504 plans.
- **ELL Scaffolding** -- language scaffolds, sentence frames, and vocabulary support for English Language Learners.
- **Gifted Extensions** -- enrichment activities and deeper challenges for advanced students.

These are generated as separate DOCX files alongside the main lesson. You can also use the `differentiate` tool to generate accommodations for any existing lesson on demand.

---

## Can students use it?

Yes. Claw-ED includes a separate student chatbot that lets students ask questions during or after a lesson:

- The student bot answers in your teaching voice (based on your persona).
- Responses are grounded in the specific lesson content -- no off-topic answers.
- Chat history is stored per-lesson so you can review what students asked.
- Access is through the Telegram bot or the `/api/chat` endpoint.

The student bot is designed for guided Q&A, not for generating work on behalf of students.

---

## How do I update?

Run:

```bash
pip install --upgrade clawed
```

Or if you installed with `uv`:

```bash
uv pip install --upgrade clawed
```

Your data, persona, and curriculum knowledge base are preserved across updates. Only the Claw-ED code is updated.

---

## Where do I get help?

- **GitHub Issues**: [Report bugs or request features](https://github.com/your-org/clawed/issues)
- **GitHub Discussions**: [Ask questions, share tips, show off your lessons](https://github.com/your-org/clawed/discussions)
- **BOT_SETUP.md**: [Telegram bot setup guide](BOT_SETUP.md)
- **GETTING_STARTED.md**: [First-time setup walkthrough](GETTING_STARTED.md)
- **CHOOSING_A_MODEL.md**: [Detailed model comparison and configuration](CHOOSING_A_MODEL.md)

---
