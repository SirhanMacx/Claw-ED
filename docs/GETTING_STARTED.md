# Getting Started in 5 Minutes

No technical background needed. If you can use email, you can use Claw-ED.

## 1. Install (1 minute)

Open your terminal (Mac: Terminal app, Windows: PowerShell) and run:

```bash
pip install clawed
```

## 2. First Run (1 minute)

```bash
clawed
```

Ed will walk you through setup:
- **Pick a model**: We recommend [Ollama Pro](https://ollama.com/pro) ($20/month) — best quality for the price. Free options available too.
- **Enter your API key**: One time only. Stored securely on your machine.
- **Tell Ed about you**: Name, school, subjects, grade levels.

## 3. Feed Ed Your Materials (2 minutes)

Point Ed at your lesson files — PPTX, DOCX, PDF, anything:

```bash
clawed ingest ~/Documents/MyLessons/
```

Ed reads through everything and learns:
- How you structure lessons (Do Now style, activity types, exit ticket format)
- Your vocabulary choices and scaffolding patterns
- Your images, maps, cartoons, and diagrams (extracted and catalogued)
- Your favorite primary sources and assessment formats

This runs once. After that, Ed knows your teaching voice.

## 4. Generate Your First Lesson (1 minute)

```bash
clawed lesson "Causes of the French Revolution" -g 10
```

In about 2 minutes, Ed produces:
- **Teacher lesson plan** (DOCX) with answer key and teacher scripts
- **Student handout** (DOCX) with fill-in-the-blank and scaffolding
- **Slideshow** (PPTX) with your own images from your files
- **IEP/504 accommodations** (DOCX)
- **ELL scaffolding** (DOCX)
- **Gifted extensions** (DOCX)
- **Review game** (HTML) — open in any browser
- **Learning journey** (HTML) — interactive student walkthrough
- **Research report** (Markdown) — topic deep-dive grounded in your materials

9 files. One command. In your voice.

## 5. Try Telegram (Optional)

Run Ed as a Telegram bot so you can generate lessons from your phone:

```bash
clawed bot
```

Message @YourBotName on Telegram: "Make me a lesson on Reconstruction for 8th grade" — files arrive in chat.

See [BOT_SETUP.md](BOT_SETUP.md) for setup details.

---

## What's Next?

- **Generate a full unit**: `clawed unit "World War II" -g 10 -w 3`
- **Search your materials**: Ask Ed "What do I have on the Civil War?"
- **Create an assessment**: `clawed assess "Reconstruction" --type crq`
- **Build a game**: Ask Ed "Make a Jeopardy game on the Constitution"
- **See your curriculum**: Ask Ed "Show me my curriculum map"

## Need Help?

- [Choosing a Model](CHOOSING_A_MODEL.md) — compare AI providers and costs
- [Bot Setup](BOT_SETUP.md) — Telegram bot configuration
- [Docker Setup](DOCKER_SETUP.md) — container deployment
- [GitHub Issues](https://github.com/SirhanMacx/Claw-ED/issues) — report bugs or request features
- [GitHub Discussions](https://github.com/SirhanMacx/Claw-ED/discussions) — ask questions
