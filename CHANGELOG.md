# Changelog

## v4.6.2026 (2026-04-06)

### Major release — model system, security hardening, agent autonomy

This release consolidates 36 incremental pushes from the v4.5 series
into a clean milestone. Every audit finding addressed, all version
surfaces aligned, CI green across Python, Docker, and TypeScript.

### Model system
- Default model: gemma4:31b-cloud (100% tool-call success, proven in 3-lesson test)
- Interactive /models command on Telegram (inline keyboard: provider → model)
- Model discovery module: dynamic Ollama Cloud + OpenRouter API listing
- Full Ollama Cloud catalog: 24 models with tool-use tags
- OpenRouter free model catalog: 6 curated free models
- OpenRouter tool-use routing fixed (was going to Ollama path, now native)
- OpenRouter timeout increased to 300s for free tier models
- Codex OAuth evaluated and removed (doesn't work for API calls)

### Security + hygiene
- Page auth cookie: ?token= now sets httponly cookie for 24h session
- Onboarding recommends Ollama Pro, mentions /models command
- lru-cache pinned to 10.4.3 (fixes CI TypeScript build)

## v4.5.2026.29 (2026-04-05)

### Hygiene
- Version drift eliminated: CHANGELOG, ROADMAP, pyproject.toml, PyPI all aligned
- Security tests run without localhost bypass — real 401/429 assertions
- Self-equipping gated: install_package requires teacher confirmation, README documents trust model
- README self-equipping claim scoped and explained
- Docker CI fixed (empty CLI bundle stub for hatchling)

## v4.5.2026.28 (2026-04-05)

### Global state + security tests
- Centralized path provider (clawed/paths.py)
- 18 security regression tests (auth, rate limit, SSRF)
- Exception handling narrowed in 4 startup blocks
- Architecture doc keyring name corrected
- Docker CI smoke test added

## v4.5.2026.27 (2026-04-05)

### Security hardening (audit remediation)
- Auth on ALL API routes (ingest, export, feedback, lessons, school)
- Auth on ALL HTML pages (dashboard, settings, analytics, profile, etc.)
- Health endpoint split: `/api/health` (liveness) + `/api/health/diagnostics` (auth-protected)
- Import URL lockdown: SSRF protection, localhost-only by default
- Public share pages (`/share/{token}`, `/student/{code}`) remain intentionally open

### v4.5.2026.26 (2026-04-05)
- Real rate limiting (in-memory, per-IP per-route)
- Bearer token auth for web API
- CORS restricted to localhost
- Docker defaults to 127.0.0.1
- Docker extra fixed (`.[hosted]` -> `.[all]`)
- Local QR generation (removed third-party api.qrserver.com)
- Skip-permissions now configurable via `auto_approve_tools`
- Non-localhost warning on `clawed serve`

### v4.5.2026.25 (2026-04-05)
- Multi-provider tier routing: `tier_providers: {"fast": "ollama", "deep": "anthropic"}`
- Enhanced switch_model tool: switch_provider, set_tier, list_providers

### v4.5.2026.20 (2026-04-05)
- Telegram transport switched from httpx to requests (Windows TLS fix)
- Ed never asks teacher to run commands (agentic prompt)
- Landing page rewrite (611 lines, open source tone)
- README rewrite (features list, no marketing)

### v4.5.2026 (2026-04-04)
- Agentic identity rewrite: autonomous master educator
- Teacher image integration in image pipeline
- New tools: generate_game, generate_simulation, differentiate_lesson
- Self-modification tools: modify_config, write_file, read_file
- CJK sanitizer for minimax model

### v4.4.2026 — v4.4.2026.6 (2026-04-04)
- v5 Magnum Opus: 7 phases shipped
  - Phase 1: Cross-transport sessions (CLI + Telegram share memory)
  - Phase 2: Google Drive OAuth + CLI commands + ingest tool
  - Phase 3: Browser tools (web search, navigate, research)
  - Phase 4: Quality tracker + pattern detection
  - Phase 5: Proactive Ed (gap detection, curriculum watch)
  - Phase 6: Self-equipping (pip install, custom YAML tools)
  - Phase 7: File management + workspace status
- ONNX MiniLM embedder (384-dim, binary BLOB storage)
- FTS5 two-stage search
- Karpathy wiki (compile, query, lint)
- Self-distillation (learns from ratings and edits)

### v4.3.2026.21 (2026-04-04)
- Unified teacher identity across transports
- Drive tool definitions registered
- Ed personality rewrite in prompt.py
- Think block stripping for reasoning models

### v4.3.2026.13 (2026-04-02)
- Architecture docs rewritten
- Model guide updated
- Bot setup guide updated
- Contributing guide updated

### Earlier versions
See git history for v1.x through v4.3.x releases.
