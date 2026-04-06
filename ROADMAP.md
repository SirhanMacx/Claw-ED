# Roadmap

Current version: **v4.6.2026**

## Next priorities

- [ ] Model quality — switch to Anthropic/OpenAI for lesson generation, keep Ollama for quick answers
- [ ] Visible bot mode — `clawed bot --visible` shows Telegram activity in terminal
- [ ] Image quality — full curriculum ingest with asset registry extraction
- [ ] Onboarding multi-provider — configure 2+ providers during setup
- [ ] Reduce global state coupling (injectable config objects)
- [ ] Narrow exception handling in startup/control-plane code
- [ ] Docker CI smoke test
- [ ] Auth regression tests (401/429 matrix)
- [ ] End-to-end integration test (setup → ingest → generate → export)

## Recently shipped

- [x] Multi-provider tier routing (`tier_providers`)
- [x] Security hardening (auth, rate limiting, CORS, SSRF protection)
- [x] ONNX MiniLM embeddings (384-dim, binary BLOB)
- [x] FTS5 two-stage KB search
- [x] Karpathy wiki (compile, query, lint)
- [x] Self-distillation from teacher feedback
- [x] Telegram transport (requests backend, Windows TLS fix)
- [x] 47 agent tools
- [x] Agentic identity + autonomy prompt
- [x] Landing page + README rewrite
