# Roadmap

Current version: **v5.15.2026**

## v5.16 — What's next

### Recently shipped (v5.15)
- [x] **Boundary-aware filesystem guards** — agent file tools now use `clawed.paths.path_is_within()` instead of string-prefix checks, closing prefix-sibling path escapes across workspace reads, self-modification, output organization, and material ingestion
- [x] **Runtime API token path resolution** — API token storage now resolves `EDUAGENT_DATA_DIR` at call time through `clawed.paths.api_token_path()`
- [x] **Security wording tightened** — compliance docs now describe the real local-first posture without implying formal FERPA/COPPA/GDPR certification

### Recently shipped (v4.16-v4.25)
- [x] **`mypy --strict` project-wide** — 1074 errors → 0 across 270 files, 144 files touched. Surfaced and fixed 7+ real runtime bugs (wrong imports, sync calls to async methods, tuple-as-dict access, missing None guards)
- [x] **B904 exception chaining** — 51 raise sites in `except` blocks now use `from <exc>` to preserve tracebacks. Suppression removed from ruff config
- [x] **April 2026 audit regression pass** — 38/38 previously-fixed defects re-verified in v4.13 code; zero regressions
- [x] **Version surface drift fixed** — `cli/source/package.json`, `daemon/package.json`, `docs/index.html`, `ROADMAP.md` were stuck at v4.9; all eight surfaces now track together

### Architecture cleanup
- [ ] **Database consolidation**: reduce 10 SQLite DBs to 3-4
- [ ] **Path centralization**: complete paths.py migration for all modules
- [ ] **Test coverage**: add tests for export_pptx, generation, models (30 untested modules)
- [ ] **conftest simplification**: one env var patch instead of 19 monkeypatches
- [x] **mypy CI gate**: enforce `--strict` in GitHub Actions

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
