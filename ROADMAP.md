# Roadmap

Current version: **v4.8.2026.2**

## v4.9 — Next priorities

### Semantic knowledge graph (Graphify deep integration)
- [ ] **LLM-powered entity extraction**: replace heuristic kg_extractor.py
  with semantic extraction. Source: https://github.com/safishamsi/graphify
- [ ] **Leiden community detection**: cluster related curriculum concepts
- [ ] **Multimodal extraction**: analyze PPTX diagrams/maps, not just text

### Ingestion improvements
- [ ] **DOCX weighting**: lesson plans rank higher than slide bullets
- [ ] **Dedup**: hash-based skip for same lesson in .doc + .docx + .pdf
- [ ] **Background ingest with progress**: daemon thread + Telegram updates

### Slide quality
- [ ] **Slide templates**: match teacher's existing style (fonts, colors)
- [ ] **Smarter image placement**: context-aware placement of teacher images

## Other priorities
- [ ] Codex/OpenAI OAuth pathway investigation
- [ ] Visible bot mode — `clawed bot --visible`
- [ ] Onboarding multi-provider
- [ ] End-to-end integration test (setup → ingest → generate → export)

## Recently shipped

- [x] v4.8.2026: AI writing removal (humanize.py, 70+ replacements, prompt
  ban list), image dedup (no more repeated images), curriculum visualizer
  (interactive HTML map via vis.js), unified full_ingest() pipeline,
  58K teacher images extracted, 227K KG entities, wiki auto-compilation,
  GLM 5.1 cloud support, 11 MCP tools, text sanitizer, slide-aware chunking

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
