# Claw-ED Pipeline Audit — April 9, 2026

## End-to-End Stress Test Results

### 1. INGEST PROCESS

**Supported Formats:** PDF, DOCX, PPTX, TXT, MD, SMART Notebook (.notebook), SMART Board (.xbk), ActivInspire (.flipchart), XLSX/CSV, RTF, HTML, ODT, ZIP (auto-unpack)

**How It Works:**
1. `ingest_path()` accepts a directory or file → calls `_extract_single()` per file
2. Each file → parsed to a `Document(title, content, doc_type, source_path, tags)`
3. PPTX files split by `[Slide N]` markers for semantic chunking
4. Documents analyzed for keywords → auto-categorized as `lesson_plan` or `unit_plan`
5. If categorized → contributed to corpus at quality_score=4.0

**Storage After Ingest:**
- Text chunks → `curriculum_kb.db` (74,665 chunks across 12,649 assets)
- KG entities → `kg_entities` (62,265 entities)
- KG relationships → `kg_triples` (184,007 triples)
- Corpus examples → `corpus.db` (12,912 examples)
- Images → `asset_images` (58,310 extracted images)
- URLs → `asset_links` (21,930 links)

**Current State (Jon's Windows Machine):**
```
corpus.db:        74 MB — 12,912 examples
curriculum_kb.db: 744 MB — 74,665 chunks, 62,265 entities, 184,007 triples
persona.json:     5 KB — full pedagogical fingerprint
wiki/:            259 articles compiled
```

---

### 2. HOW INGESTED FILES ARE RECALLED

**Three Recall Paths:**

#### Path A: Corpus Few-Shot Examples
- **Where:** `generate_master_content()` → `get_few_shot_context()`
- **What:** Top 2-3 highest-quality examples matching subject + content_type
- **How:** SQL query on `corpus_examples` ordered by `quality_score DESC`
- **Subject Matching:** Alias map resolves "US History" → "social studies", "biology" → "science", etc.
- **Result:** 4,290 chars of context injected into prompt at `{few_shot_context}`
- **Status: WORKING** — US History, Global History, and Science all return 3 examples

#### Path B: Knowledge Graph Connections
- **Where:** `generate_master_content()` → `inject_connections_into_prompt()`
- **What:** Related topics, prerequisites, cross-unit links from KG
- **How:** `CurriculumKG.query_related(teacher_id, topic)` → SQL on `kg_triples`
- **Bug Found:** teacher_id mismatch. Triples stored as "default", queried as "teacher-ce38eb1fbdfd"
- **Fix Applied:** Falls back to "default" if teacher-specific query returns nothing
- **Status: FIXED** — Renaissance now returns 68 connections, reform movements returns 3

#### Path C: Curriculum KB Semantic Search
- **Where:** Used by tools like `search_my_materials`, `query_knowledge_graph`
- **What:** Full-text search across 74,665 chunks with FTS5
- **How:** Teacher asks a question → KB searches chunks → returns relevant excerpts
- **Status: WORKING** — FTS index exists, 74,665 chunks indexed

---

### 3. HOW IMAGES ARE USED

**Image Extraction During Ingest:**
- PPTX/DOCX images extracted via `extract_rich()` → stored in `asset_images` table
- 58,310 images extracted from Jon's materials
- Images stored as blobs with metadata (source_path, slide_number, dimensions)

**Image Use During Compilation:**
- `MasterContent` has `image_spec` fields on primary_sources, direct_instruction, vocabulary
- `image_spec` is a SEARCH QUERY string (e.g., "Thomas Nast political cartoon 1871")
- `fetch_all_images(master)` resolves specs to local files:
  1. **Phase 1:** Check teacher's own extracted images via semantic search on asset_registry
  2. **Phase 2:** Fetch from external sources if no local match
  3. **Phase 3:** Vision model quality filter (GOOD/ACCEPTABLE/REJECT)
- Resolved images embedded into DOCX at compile time

**Current Gap:**
- 58,310 images extracted but **0 cached images** in the runtime cache
- Image fetching happens at compile time, NOT pre-cached
- If no internet connection at compile time, lessons compile WITHOUT images
- Teacher's own extracted images are in `asset_images` but the pipeline to match
  `image_spec` queries against them needs semantic embeddings (which may not be generated)

---

### 4. HOW TEACHER VOICE IS USED

**Persona Extraction:**
- After ingest, LLM analyzes sample documents → extracts `TeacherPersona`
- Stored in `~/.eduagent/persona.json`
- Merged with existing persona on each subsequent ingest (union, not replace)

**Jon's Extracted Persona (actual data):**
```
Teaching style: direct_instruction
Tone: "warm, structured, and encouraging"
Writing framework: "Claim and Evidence"
Do Now style: "Opinion or reflection questions connecting to prior knowledge"
Exit ticket: "Teacher-led verbal closure reviewing handout questions"

Strategies: [
  "direct instruction via PowerPoint",
  "guided questioning",
  "primary source analysis",
  "mock trials"
]

Source types: [
  "political party platforms",
  "historical treatises and documents",
  "news articles and editorials",
  "statistical data tables and charts"
]

Voice sample: "As you sit in class you are carrying your 'effects.'
You have personal belongings in your pocket, purse, or backpack..."

Signature moves: [
  "Defines the exact cognitive verb before asking students to perform the task",
  "Bridges abstract constitutional concepts to students' immediate physical reality",
  "Structures lessons around PowerPoint → handout → teacher-led answer check"
]

Scaffolding moves: [
  "Provides explicit definitions of task verbs in assessments",
  "Uses relatable, real-world analogies to introduce complex concepts",
  "Provides step-by-step procedural checklists for complex tasks"
]
```

**How Persona Flows Into Generation:**
1. `_build_system_prompt()` calls `persona.to_prompt_context()` → serializes all fields
2. System prompt includes: teaching style, tone, structural preferences, voice sample
3. LLM receives persona as SYSTEM prompt, lesson request as USER prompt
4. Quality gate enforces persona alignment: checks for hooks, personality, CFU questions

**Verification:** The Industrial Revolution lesson's teacher script contained:
- "As you sit in class you are carrying your 'effects'" — DIRECTLY from voice sample
- "Britain sat on top of coal the way Texas sits on top of oil" — real-world analogy (signature move)
- "When completing this assessment keep the following definition in mind: explain means..." — cognitive verb definition (signature move)

**The persona IS flowing through.** The LLM is picking up Jon's patterns.

---

### 5. GAPS AND ISSUES FOUND

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | KG teacher_id mismatch — 0 connections returned | P0 | **FIXED** |
| 2 | KG entity quality — garbage entries from OCR artifacts | P1 | Open |
| 3 | No `prerequisite_for`/`builds_on` predicates — all `related_to` | P1 | Open |
| 4 | 58,310 images extracted but 0 cached at runtime | P1 | Open |
| 5 | State DB records 0 generated lessons | P2 | Open |
| 6 | Corpus quality_score never updated from feedback | P2 | Open |
| 7 | KG embeddings may not be generated for semantic search | P2 | Open |
| 8 | Persona name is generic "My Teaching Persona" | P3 | Open |

### 6. RECOMMENDATIONS

1. **KG Entity Cleanup:** Run a one-time cleanup pass on `kg_entities` to remove entries with:
   - Newlines in names
   - Entries shorter than 3 characters
   - Entries that are just formatting artifacts ("______", ":", ",")

2. **KG Predicate Enrichment:** The extractor only creates `related_to` relationships. Need to add logic to detect `prerequisite_for` when lesson ordering is clear (e.g., "Unit 1 Lesson 3" builds_on "Unit 1 Lesson 2").

3. **Image Pre-Cache:** After ingest, pre-cache the top 100 most-relevant images for each unit topic so they're available at compile time without internet.

4. **State Tracking:** Wire `generate_master_content()` to record each generation in `state.db` so we can track what's been generated and avoid duplicates.
