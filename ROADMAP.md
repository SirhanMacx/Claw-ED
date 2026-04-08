# Roadmap

Current version: **v4.7.2026.10**

## v4.8 — Human voice + slide quality

### AI writing removal
- [ ] **avoid-ai-writing integration**: strip AI-isms from generated content
  before compiling to DOCX/PPTX. 109-word replacement table (3 tiers),
  36 detectable patterns. Ed's output should read like the teacher wrote it.
  Source: https://github.com/conorbronsdon/avoid-ai-writing
- [ ] **Prompt-level avoidance**: inject Tier 1 word ban list into Ed's
  system prompt so the LLM avoids AI-isms from the start
- [ ] **Post-generation rewrite pass**: run rewrite mode on MasterContent
  text before DOCX/PPTX compilation

### Ingestion improvements
- [ ] **DOCX weighting**: lesson plans (DOCX) should rank higher than
  slide bullets (PPTX) in search results. Add content_type boost.
- [ ] **Dedup**: same lesson in .doc + .docx + .pdf gets indexed 3x.
  Hash-based skip for identical content across formats.
- [ ] **Background ingest with progress**: teacher shouldn't wait —
  ingest in daemon thread with Telegram progress updates.

### Slide quality
- [ ] **Slide templates**: match the teacher's existing slide style
  (fonts, colors, layout) from ingested PPTX files.
- [ ] **Richer PPTX output**: intelligently place teacher's diagrams,
  maps, and source images in generated slides.

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
