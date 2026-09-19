# Getting started

Use Python 3.11 or newer. Follow the [README installation steps](../README.md#setup) to create a virtual environment and install `clawed`.

1. Run `clawed setup` and select a provider. [Choose a model](CHOOSING_A_MODEL.md) using the current local, budget, and premium options. Hosted usage is billed separately; local inference requires a downloaded model and enough memory.
2. Import a small folder of your own permitted PDF, DOCX, PPTX, TXT, or Markdown materials with `clawed ingest ./my-lessons/`. Check the extracted text; ingestion cannot guarantee that every layout or source location survives.
3. Run `clawed` for an interactive request, or `clawed serve` for the local dashboard. No Node.js installation is needed.
4. For a recoverable lesson bundle, open **Jobs**, enter a topic, subject, and grade, and queue the draft. Start `clawed queue worker` in another terminal. Jobs do not run while the worker is stopped.
5. Inspect the source manifest, teacher plan, student packet, and slides. Check every quotation and answer against the supplied sources, then edit the documents before sharing.

A failed worker can be recovered after five minutes without a heartbeat. Use **Recover interrupted jobs**, then **Resume draft**. Matching completed phases are reused. Cancellation cannot undo a request already running at your model provider.

Configuration normally lives in `~/.eduagent/`; exports normally live in `~/clawed_output/`. Hosted models receive selected content. Keep private student information out of material sent to services unless your school has approved that use. Telegram and external sharing require their own setup; start the bot explicitly with `clawed bot`.

See [troubleshooting](TROUBLESHOOTING.md) for setup problems and [the architecture](ARCHITECTURE.md) for recovery limits.
