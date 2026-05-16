# Security & Privacy

Claw-ED is a local-first tool designed for teachers. Your data stays on your machine.

## Data Residency

- **Lesson plans, slides, and handouts** are saved to `~/clawed_output/` on YOUR machine
- **Curriculum knowledge base** is stored in local SQLite at `~/.eduagent/memory/`
- **Teacher images** extracted from your PPTX files stay in `~/.eduagent/cache/extracted/`
- **Nothing is uploaded to our servers** — we don't have servers
- The only external calls are to the LLM provider YOU choose (Ollama, Anthropic, OpenAI, Google, or OpenRouter)

## API Key Storage

- API keys are stored in `~/.eduagent/secrets.json` with `0600` file permissions (owner-only access)
- On macOS, keys can optionally use the system Keychain via `pip install clawed[keyring]`
- Keys are NEVER logged, transmitted, or included in generated output

## Student Data

- The optional student bot runs on YOUR machine
- Student questions and interactions are stored locally in `~/.eduagent/state.db`
- No student data is sent anywhere without explicit teacher-initiated export
- The student bot does not collect names, emails, or identifying information

## Compliance

Claw-ED is designed for local-first, teacher-controlled use, but it is not a
formally certified FERPA/COPPA/GDPR compliance product.

- Do not use Claw-ED with identifiable student records, IEP/504 documents,
  school-issued accounts, or district-restricted data unless your district has
  approved that workflow.
- Student interactions stay on the teacher's machine by default, but cloud LLM
  providers receive prompts when you choose a cloud model.
- State education data laws vary. Check your district and state requirements
  before using any AI tool with student data.

## Self-Equipping Safety

Claw-ED can install Python packages when it needs a new capability (e.g., Manim for animations). This is:
- Limited to `--user` scope (never system-wide)
- Logged in the terminal for teacher visibility
- Requires teacher confirmation for the initial install
- Blocked for built-in Python modules (os, sys, subprocess, etc.)

## Reporting Security Issues

**Do NOT open a public GitHub issue for security vulnerabilities.**

Email: jon.anthony.maccarello@gmail.com with subject line "SECURITY: [brief description]"

We will respond within 48 hours and work with you to address the issue before any public disclosure.
