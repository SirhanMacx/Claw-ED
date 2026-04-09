# Claw-ED v2.3.7 Release Notes

**Date:** 2026-03-29
**Theme:** Images that work, search that finds, security that protects.

---

## Summary

v2.3.7 is the largest hardening release since the Master Content Track rewrite. It addresses the top issues from Sirhan testing, adds 12 new file formats, fixes 3 critical search bugs, and closes every security finding from the pre-release audit.

1. **Images in every lesson.** Required image specs, three-stage teacher image matching, subject-aware external search.
2. **Search actually surfaces results.** Cross-transport teacher ID fallback, error logging, explicit agent instructions.
3. **12 new file formats.** Legacy .doc, .ppt, .xls and 9 others now parsed. Teacher archives are no longer 93% invisible.
4. **Background ingestion.** Non-blocking, with progress updates and per-file error resilience.
5. **Security hardened.** Path traversal, XSS, race conditions, ZIP bombs, debug info leaks — all fixed.
6. **50 MB lighter install.** Removed unused anthropic/openai SDKs.

---

## Changes

### Image Pipeline

- `image_spec` REQUIRED for all primary sources and direct instruction sections (all subjects, not just Science/Social Studies)
- Three-stage progressive teacher image matching: full query → individual keywords → subject fallback
- Filename matches weighted 3x vs content matches, exact phrase bonus +5, up to 150 candidates scored
- Subject flows through entire pipeline: image_pipeline.py → slide_images.py → teacher search
- 30-day image cache cleanup on session start
- Pydantic validators warn on empty image_spec (don't break generation)
- Prompt guidance on writing effective image specs (format, specificity, grade context)

### Search & Ingestion

- **BUG 6 fixed**: Cross-transport teacher_id fallback (`search_all_teachers()`), bare except replaced with logging, agent prompt requires surfacing results
- **BUG 7 fixed**: 12 new file extensions (`.doc`, `.ppt`, `.xls`, `.xlsx`, `.csv`, `.rtf`, `.html`, `.htm`, `.odt`, `.odp`). Uses macOS textutil, openpyxl, stdlib csv/HTMLParser, ODF XML extraction
- **BUG 8 fixed**: Topic tags auto-extracted from filename + content keywords, stored as JSON, included in search scoring
- TF-IDF vocabulary capped at 10,000 tokens
- KB search limit raised from 2,000 to 5,000 chunks
- Background ingestion: non-daemon thread, semaphore (max 3), per-file error resilience
- Failed files logged and counted in completion summary

### Security

- Path traversal protection on `read_workspace` (resolve + containment)
- `read_file` path bypass fixed (resolved path containment, not string prefix)
- `ingest_materials` restricted to home directory with 500-file cap
- XSS escaping on all dynamic content in web dashboard
- TOOL_DEFINITIONS race condition fixed with threading.Lock
- ZIP bomb protection (500 MB decompressed size limit)
- Debug info masked from user-facing error messages
- `dashboard_password` added to _SECRET_FIELDS

### Dependencies & Config

- Removed `anthropic` and `openai` from dependencies (~50 MB savings)
- Added `lxml` to dependencies (used by python-pptx)
- Added `qrcode` to optional `[qr]` group
- API key resolution unified: `config.get_api_key()` (env var + keyring + secrets) used everywhere
- Model router updated: Haiku 4.5, Sonnet 4.6, Opus 4.6

### Tests

1580 passed, 31 skipped, 0 failed. New coverage:
- Ingest path outside-home rejection test
- master_content in DEEP tier assertion
- Version assertions updated

---

## What's Next

Remaining from v2.3.6 plan:
- **Phase 3:** GitHub Actions CI pipeline + critical module test coverage (55% → 65%)
- **Phase 4 partial:** Student DOCX image embedding, few-shot example length increase
- Image pipeline dedicated test suite
- Background ingestion threading tests
- Database consolidation (4 SQLite DBs → 1)
