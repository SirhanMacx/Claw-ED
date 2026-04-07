# Roadmap

Current version: **v4.6.2026**

## v4.7 — Ingestion overhaul + image pipeline

The KB has 560K+ chunks but zero teacher images. PPTX files (99.5% of
chunks) contain the images but the current ingest only extracts text.

### Ingestion fixes
- [ ] **Asset extraction pipeline**: use `clawed ingest` full pipeline
  (parse → extract images → register assets → index chunks) instead
  of manual `kb.index()`. The PPTX files have maps, political cartoons,
  diagrams, timelines — all need to go into the asset registry.
- [ ] **Content-type aware chunking**: PPTX slides should be 1 chunk
  per deck (concatenate slides) not 1 chunk per 500 words. Slide bullet
  points dilute search — the full deck is the meaningful unit.
- [ ] **DOCX weighting**: lesson plans (DOCX) should rank higher than
  slide bullets (PPTX) in search results. Add content_type boost.
- [ ] **Dedup**: same lesson in .doc + .docx + .pdf gets indexed 3x.
  Hash-based skip for identical content across formats.
- [ ] **Quality filter**: skip chunks that are mostly headers, footers,
  or boilerplate (< 100 words of real content).
- [ ] **Background ingest with progress**: teacher shouldn't wait —
  ingest in daemon thread with Telegram progress updates.

### Image pipeline
- [ ] **Teacher image priority**: image_pipeline.py checks AssetRegistry
  first but the registry is empty. Once assets are extracted from PPTX,
  teacher's own images (maps, cartoons, photos) should appear in generated
  lessons instead of generic LOC/Wikimedia stock.
- [ ] **Image relevance scoring**: match image context_text against
  lesson topic, not just keyword matching.

### Slide quality
- [ ] **Richer PPTX output**: current slides are basic text + stock
  images. With teacher images available, slides should use the teacher's
  actual diagrams, maps, and source images.
- [ ] **Slide templates**: match the teacher's existing slide style
  (fonts, colors, layout) from ingested PPTX files.

## Other priorities
- [ ] Codex/OpenAI OAuth pathway investigation
- [ ] Visible bot mode — `clawed bot --visible`
- [ ] Onboarding multi-provider
- [ ] End-to-end integration test (setup → ingest → generate → export)

## Recently shipped

- [x] v4.6.2026: Gemma 4 31B default, interactive /models, 24 Ollama +
  6 OpenRouter models, multi-provider tier routing, full security
  hardening, 21 auth tests, ONNX embeddings, FTS5 search, Karpathy wiki,
  self-distillation, 47 agent tools, CI fully green
