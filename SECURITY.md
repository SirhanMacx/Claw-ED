# Security & Privacy

Claw-ED stores its working data locally. The providers and integrations you enable
determine which content leaves your machine.

## Data Residency

- **Lesson plans, slides, and handouts** are saved to `~/clawed_output/` on YOUR machine
- **Curriculum knowledge base** is stored in local SQLite at `~/.eduagent/memory/`
- **Teacher images** extracted from your PPTX files stay in `~/.eduagent/cache/extracted/`
- **Nothing is uploaded to our servers** — we don't have servers
- Cloud LLM providers receive generation and chat prompts. Image search, web
  research, Telegram, and Drive integrations also make external requests when used.

## API Key Storage

- API keys are stored in `~/.eduagent/secrets.json` with `0600` file permissions (owner-only access)
- On macOS, keys can optionally use the system Keychain via `pip install clawed[keyring]`
- Provider keys are sent to the configured provider to authenticate requests;
  they should not be included in prompts or generated output.

## Student Data

- The optional student bot runs on YOUR machine
- Web chat messages are stored in `clawed_data/clawed.db`, or in `clawed.db`
  under `EDUAGENT_DATA_DIR` when configured. Other bot state uses `~/.eduagent/state.db`.
- Chat questions, recent conversation history, and lesson context are sent to the
  configured model. A cloud model therefore receives this content without an export.
- The widget does not ask for names or email addresses, but students can include
  identifying information in free-text questions.
- Each web chat conversation uses a random token scoped to its lesson and audience.
  Separate students do not receive each other's stored conversation history. The
  server stores only a hash of the token. The widget keeps its token in memory;
  reloading the page starts a new conversation. Treat share links as access grants.

## Dashboard and Tool Permissions

- The dashboard uses an HttpOnly, SameSite=Strict session cookie. Cookie-authenticated
  API mutations require a matching Origin or Referer. API clients can use a bearer
  token. Localhost authentication bypass requires an explicit environment setting.
- Student-widget CORS access applies only to `/api/chat/student`; it does not grant
  access to teacher routes, and every student request still needs a lesson share token.
- Action approvals cover one requesting teacher, tool, and exact parameter set.
  They expire after the configured timeout and are consumed before execution, so
  a failed action needs a fresh approval before retrying. Legacy unscoped grants
  cannot authorize new actions.
- File tools may access workspace and export files, but cannot access the other
  application-state directories, even through symlinks or overlapping export roots.

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
- Requires a fresh, specific teacher approval for each install action
- Blocked for built-in Python modules (os, sys, subprocess, etc.)

## Reporting Security Issues

**Do NOT open a public GitHub issue for security vulnerabilities.**

Email: jon.anthony.maccarello@gmail.com with subject line "SECURITY: [brief description]"

We will respond within 48 hours and work with you to address the issue before any public disclosure.
