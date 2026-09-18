# Claw-ED

> Your curriculum. Your teaching voice. Lessons you can review and edit.

Claw-ED is a local-first AI teaching assistant. Start with your existing lesson plans, slides, and assessments; use them to draft new lessons, student materials, and presentations. You choose the model and review the result before using or sharing it.

**Current release: v9.18.2026 · Beta · Python 3.11+**

[Install](#setup) · [Website](https://sirhanmacx.github.io/Claw-ED/) · [Release notes](CHANGELOG.md) · [Security and privacy](SECURITY.md) · [Report an issue](https://github.com/SirhanMacx/Claw-ED/issues)

## Start with one lesson

1. **Bring your materials.** Import a folder of PDF, DOCX, PPTX, TXT, or Markdown files. Claw-ED extracts text, indexes material for retrieval, and builds a teaching-style profile.
2. **Give it a concrete task.** Specify the topic, class, learning objective, and materials you need. Existing material and your saved profile can inform the draft.
3. **Review the outputs.** Check source accuracy, answer keys, pacing, accessibility, and layout. Edit the DOCX and PPTX files in your usual tools.
4. **Choose what to deliver.** Keep files locally or use configured integrations. Student access and external publication need deliberate setup.

The lesson bundle tool creates a teacher DOCX, student DOCX, and PPTX slides. Optional extensions can add differentiated materials, games, and other formats. The actual result depends on the request, model, installed extras, and successful exports; a fixed file count is not guaranteed.

## Setup

Use Python 3.11 or newer in a virtual environment:

```bash
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade clawed
clawed setup
```

Choose a provider and configure access in the setup wizard. Then try the Python commands:

```bash
clawed ingest ./my-lessons/
clawed lesson "Causes of the French Revolution" -g 10 -s "Global History"
clawed serve                         # local dashboard and API
clawed --version
```

Run `clawed` for interactive use. The terminal interface uses the bundled Node interface when Node.js is available and falls back to the Python CLI otherwise. `clawed --python` selects the Python path explicitly. For command-specific options, use `clawed <command> --help`.

[Getting started](docs/GETTING_STARTED.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)

## What is available today

| Area | What it provides | What to check |
| --- | --- | --- |
| Curriculum ingestion | Text extraction, search, teaching-style profiles, and image extraction | Retrieval may miss or shorten relevant material; inspect the sources used |
| Lesson production | Structured lesson content, teacher/student documents, and slides | Factual accuracy, source attribution, answer keys, and classroom fit |
| Quality checks | Section, source-text, differentiation, and assessment checks with bounded repair attempts | These are automated checks, not proof that a lesson is ready to teach |
| Dashboard and API | Local lesson views, teacher chat, exports, and student embed snippets | Teacher authentication and correct share-link setup |
| Integrations | Telegram, Google Drive, Classroom-related tools, and MCP | Provider credentials, permissions, and destination readback |
| Experimental features | Games, simulations, scheduling, live classroom sessions, and student-facing tools | Feature-specific limitations; some session state does not survive restarts |

The release is intended for a single teacher per instance. It is not a multi-tenant school platform. Student-facing features remain experimental within Claw-ED.

## What v9.18.2026 changes

- Separate chat histories by conversation, lesson, and teacher/student audience.
- Require exact, expiring, single-use approvals for protected actions and keep file tools out of protected application state.
- Restore dashboard cookie authentication and repair student widget embeds.
- Run the final quality gate on both main lesson-generation paths.
- Verify the three core bundle exports and report incomplete delivery as partial, failed, or draft.

Existing lessons and chat rows are preserved. Old unscoped approvals need a fresh request; recopy student widget snippets after upgrading. See the [changelog](CHANGELOG.md) for migration details.

## Models and privacy

Provider adapters support Anthropic, OpenAI, Google Gemini, Ollama, and OpenRouter. Model support and tool behavior vary by provider and task. API pricing, quotas, and model availability are set by the provider; Claw-ED does not include model usage.

Configuration and working data are stored locally under `~/.eduagent/` by default. **Local storage does not mean all processing stays on the device.** Hosted models receive the prompts and selected content needed for a request. Web search, image retrieval, Telegram, Google integrations, and package installation also contact their respective services when used.

For local inference, configure a locally running model and avoid cloud providers and network-dependent features. Review what you ingest and share; remove student identifiers where possible. The application is not a certification of compliance with school data policies.

Teacher web routes require authentication. The dashboard uses an HttpOnly session cookie with same-origin checks on changes; API clients can use a bearer token. Student embeds use lesson share tokens and separate conversation tokens. Keep the server local unless you have configured access controls for the intended audience.

Read [SECURITY.md](SECURITY.md) for the trust boundary and reporting process.

## Useful commands

```bash
clawed                                  # interactive assistant
clawed ingest ./my-lessons/              # import teaching materials
clawed lesson "Topic" -g 8 -s "History"  # draft a lesson
clawed unit "Topic" -g 9 -w 3            # draft a multi-week unit
clawed assess "Topic" --type crq         # draft an assessment
clawed kb query "question"               # search the curriculum wiki
clawed bot                              # Telegram interface
clawed serve                            # local dashboard and API
clawed drive auth                       # configure Google Drive access
clawed schedule list                    # inspect configured schedules
clawed mcp-server                       # expose tools to an MCP client
```

## Development

```bash
git clone https://github.com/SirhanMacx/Claw-ED.git
cd Claw-ED
python -m pip install -e ".[dev]"
ruff check .
mypy --strict clawed
pytest tests/
```

CI exercises Python 3.11 and 3.12, the TypeScript build, wheel installation, and Docker startup. Most tests use synthetic data or mocked model responses; passing CI does not establish teaching quality across live models. The bundled terminal build additionally uses Node.js and Bun; see [cli/README.md](cli/README.md).

Useful contributions include reproducible bugs, teacher-reviewed sample lessons, source-fidelity checks, and improvements to a complete import → draft → review → export workflow. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [roadmap](ROADMAP.md).

Claw-ED's original code is released under the [MIT license](LICENSE). Third-party components retain their own terms. The project is maintained by [MacxLabs](https://macxlabs.app/?src=github-claw-ed-readme); [supporting development](https://macxlabs.app/support/?src=github-claw-ed-readme) is optional.
