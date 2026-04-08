# Roadmap

Current version: **v4.7.2026.9**

## v4.8 — Ingestion overhaul + slide quality

### Ingestion fixes
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

### Slide quality
- [ ] **Slide templates**: match the teacher's existing slide style
  (fonts, colors, layout) from ingested PPTX files.
- [ ] **Richer PPTX output**: with teacher images flowing, slides should
  intelligently place the teacher's diagrams, maps, and source images.

## Other priorities
- [ ] Codex/OpenAI OAuth pathway investigation
- [ ] Visible bot mode — `clawed bot --visible`
- [ ] Onboarding multi-provider
- [ ] End-to-end integration test (setup → ingest → generate → export)

## Recently shipped

- [x] v4.7.2026: Teacher image pipeline fixed (31K+ images now flow into
  generated lessons), semantic image matching via ONNX embeddings, topic-tag
  enrichment from curriculum folder structure, teacher-first image lookup in
  both generate_lesson_bundle and export_pptx paths, animated educational
  videos via Manim (timelines, concept maps, cause-effect diagrams, process
  flows, Venn comparisons, vocabulary cards), 6 animation templates,
  generate_animation tool auto-discovered, `pip install clawed[animations]`
  optional dependency

- [x] v4.6.2026: Gemma 4 31B default, interactive /models, 24 Ollama +
  6 OpenRouter models, multi-provider tier routing, full security
  hardening, 21 auth tests, ONNX embeddings, FTS5 search, Karpathy wiki,
  self-distillation, 47 agent tools, CI fully green
