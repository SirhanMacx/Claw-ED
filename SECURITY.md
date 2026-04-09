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

- **FERPA compatible** — no student education records are transmitted or aggregated
- **COPPA compatible** — student interactions stay on the teacher's machine
- **GDPR compatible** — local-first architecture with no data collection
- **State education data laws** — check your state's requirements for AI tools in education

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
