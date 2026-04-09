# Roadmap

Current version: **v4.9.2026.9**

## v4.9 — Architecture + Ecosystem

### Architecture cleanup (from audit)
- [ ] **Database consolidation**: reduce 10 SQLite DBs to 3-4
- [ ] **Path centralization**: complete paths.py migration for all modules
- [ ] **Test coverage**: add tests for export_pptx, generation, models (30 untested modules)
- [ ] **conftest simplification**: one env var patch instead of 19 monkeypatches

### Semantic knowledge graph (Graphify)
- [ ] **LLM-powered entity extraction**: replace heuristic kg_extractor.py
  Source: https://github.com/safishamsi/graphify
- [ ] **Leiden community detection**: cluster related curriculum concepts
- [ ] **Actionable curriculum map**: gap analysis, prerequisite chains, material links

### Teacher experience
- [ ] **Slide template matching**: extract fonts/colors from teacher's PPTX
- [ ] **Year planner**: generate full 180-day curriculum from standards
- [ ] **Lesson revision tool**: improve one section without full regeneration
- [ ] **Student performance tracking**: integrate with Google Classroom/Canvas
- [ ] **Real-time classroom mode**: teacher controls journey step-by-step

### Growth
- [ ] **Demo GIF**: 30-second terminal recording for README
- [ ] **YouTube walkthrough**: 2-minute setup + generation demo
- [ ] **Product Hunt launch**: prep listing + materials
- [ ] **School district pilot**: 3 schools, compliance docs, training template
- [ ] **Chrome extension**: quick lesson gen from any webpage

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
