"""Teacher STYLE PROFILES — learn a teacher's voice, lesson structure, and
conventions from their own materials, then condition every generation on it.

The killer ingest feature: point Claw-ED at a folder of real lesson files
and from then on everything it writes matches THAT teacher — their Do-Now
openers, their guided-notes curtness, their answer-key habits.

Design:
- **Deterministic skeleton, LLM-filled fields.** Section detection, question
  types, point values, scaffolds, sentence stats, and exemplar excerpts are
  computed with regex heuristics (testable, offline). The LLM only writes
  the qualitative voice fields — and every LLM failure degrades to a
  heuristic fallback, never a broken profile.
- **Per-file cache by content hash** so re-ingesting a folder only analyzes
  new/changed files (incremental, cheap).
- **Local-first privacy.** Profiles and caches live on disk under the
  agent's data dir. Only short excerpts of files are ever sent to the
  teacher's own configured LLM provider during analysis.
- **Multi-profile.** A teacher may keep one profile per course; exactly one
  (or none — the default MacxLabs style) is *active* at a time.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from clawed.paths import data_dir

logger = logging.getLogger(__name__)

# How much of each file the LLM may see (privacy + token budget).
_LLM_EXCERPT_CHARS = 5_000
# At most this many files get an LLM pass per ingest; the rest are
# heuristics-only. Cached analyses don't count against the budget.
_MAX_LLM_FILES = 40
_EXEMPLAR_CHARS = 420
_MAX_EXEMPLARS = 8


class _SupportsGenerateJSON(Protocol):
    # Returns Any: LLMClient.generate_json is annotated dict but json_repair
    # can hand back lists — callers must isinstance-check the shape.
    async def generate_json(
        self, prompt: str, system: str = "", temperature: float = 0.4,
        max_tokens: int = 8192, demo_hint: str = "",
    ) -> Any: ...


# ── Schema ───────────────────────────────────────────────────────────


class StyleExemplar(BaseModel):
    """A short, representative excerpt used for few-shot grounding."""

    category: str  # do_now | directions | assessment_question | rubric | voice
    source: str    # file name it came from (never the full path in prompts)
    snippet: str


class SectionPattern(BaseModel):
    """One recurring lesson section, with how often it appears."""

    name: str
    count: int
    frequency: float  # 0..1 share of lesson-like docs containing it
    avg_position: float = 0.5  # mean relative position within the doc (0=top)


class StyleProfile(BaseModel):
    """Everything Claw-ED learned about how this teacher writes materials."""

    profile_id: str
    name: str
    source_path: str
    created_at: str
    updated_at: str
    files_analyzed: int = 0
    files_skipped: int = 0

    # Voice / tone
    voice_tone: str = ""            # e.g. "direct" / "ornate" / "warm"
    voice_person: str = ""          # e.g. "second person ('you')"
    voice_register: str = ""        # e.g. "plain classroom language"
    sentence_style: str = ""        # e.g. "short, curt (avg 9 words/sentence)"
    voice_description: str = ""     # readable paragraph (LLM, with fallback)

    # Formatting conventions
    formatting: list[str] = Field(default_factory=list)

    # Lesson structure
    lesson_structure: list[SectionPattern] = Field(default_factory=list)
    structure_summary: str = ""

    # Assessment style
    question_types: list[str] = Field(default_factory=list)
    point_values: list[str] = Field(default_factory=list)
    rubric_language: list[str] = Field(default_factory=list)
    answer_key_style: str = ""
    mc_letter_note: str = ""

    vocabulary_level: str = ""
    scaffolds: list[str] = Field(default_factory=list)
    exemplars: list[StyleExemplar] = Field(default_factory=list)


# ── Storage ──────────────────────────────────────────────────────────


def profiles_dir() -> Path:
    return data_dir() / "style_profiles"


def _cache_dir() -> Path:
    return profiles_dir() / "cache"


def _active_path() -> Path:
    return profiles_dir() / "active.json"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "profile"


def save_profile(profile: StyleProfile) -> Path:
    profiles_dir().mkdir(parents=True, exist_ok=True)
    path = profiles_dir() / f"{profile.profile_id}.json"
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_profile(profile_id: str) -> StyleProfile | None:
    path = profiles_dir() / f"{profile_id}.json"
    if not path.is_file():
        return None
    try:
        return StyleProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Corrupt style profile %s: %s", profile_id, exc)
        return None


def list_profiles() -> list[StyleProfile]:
    if not profiles_dir().is_dir():
        return []
    profiles = []
    for f in sorted(profiles_dir().glob("*.json")):
        if f.name == "active.json":
            continue
        p = load_profile(f.stem)
        if p is not None:
            profiles.append(p)
    return profiles


def delete_profile(profile_id: str) -> bool:
    path = profiles_dir() / f"{profile_id}.json"
    if not path.is_file():
        return False
    if get_active_profile_id() == profile_id:
        set_active_profile(None)
    path.unlink()
    return True


def set_active_profile(profile_id: str | None) -> None:
    """Set the active profile, or None for the default MacxLabs style."""
    profiles_dir().mkdir(parents=True, exist_ok=True)
    _active_path().write_text(
        json.dumps({"active": profile_id}), encoding="utf-8",
    )


def get_active_profile_id() -> str | None:
    try:
        raw = json.loads(_active_path().read_text(encoding="utf-8"))
        pid = raw.get("active")
        return str(pid) if pid else None
    except (OSError, ValueError):
        return None


def get_active_profile() -> StyleProfile | None:
    pid = get_active_profile_id()
    return load_profile(pid) if pid else None


# ── Per-file analysis cache (content-hash keyed → incremental) ───────


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:32]


def cache_get(content_hash: str) -> dict[str, Any] | None:
    path = _cache_dir() / f"{content_hash}.json"
    if not path.is_file():
        return None
    try:
        result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return result
    except (OSError, ValueError):
        return None


def cache_put(content_hash: str, analysis: dict[str, Any]) -> None:
    _cache_dir().mkdir(parents=True, exist_ok=True)
    (_cache_dir() / f"{content_hash}.json").write_text(
        json.dumps(analysis), encoding="utf-8",
    )


# ── Deterministic heuristics ─────────────────────────────────────────

# Canonical lesson sections, in the order teachers usually run them.
# Matched case-insensitively at line starts or as labeled headers.
SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Do Now", re.compile(r"\bdo[\s-]?now\b", re.I)),
    ("Aim/Objective", re.compile(r"^\s*(aim|objective|learning (?:target|objective)|swbat)\b[:.]?", re.I | re.M)),
    ("Vocabulary", re.compile(r"^\s*(vocabulary|key terms?|word bank)\b", re.I | re.M)),
    ("Mini-lesson/Notes", re.compile(
        r"\b(mini[\s-]?lesson|guided notes|box notes|notes packet|cornell notes)\b", re.I)),
    ("Directions", re.compile(r"^\s*directions?\s*[:.]", re.I | re.M)),
    ("Document Analysis", re.compile(
        r"\b(document analysis|primary source|according to (?:this|the) document"
        r"|based on (?:this|the) document)\b", re.I)),
    ("Activity", re.compile(r"^\s*(activity|task|station|group work|jigsaw)\b", re.I | re.M)),
    ("Film/Video Questions", re.compile(r"\b(film questions?|video questions?|while watching)\b", re.I)),
    ("CRQ/Constructed Response", re.compile(r"\b(crq|constructed[\s-]?response|short[\s-]?answer question)\b", re.I)),
    ("Exit Ticket", re.compile(r"\b(exit (?:ticket|slip)|ticket out)\b", re.I)),
    ("Homework", re.compile(r"^\s*(homework|hw)\b[:.]?", re.I | re.M)),
    ("Answer Key", re.compile(r"\b(answer key|teacher (?:copy|key|version)|exemplar|answers?:)\b", re.I)),
]

_SCAFFOLD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("word banks", re.compile(r"\bword bank\b", re.I)),
    ("sentence starters", re.compile(r"\bsentence (?:starters?|stems?|frames?)\b", re.I)),
    ("graphic organizers", re.compile(r"\b(graphic organizer|t[\s-]?chart|venn diagram|concept map)\b", re.I)),
    ("annotation prompts", re.compile(
        r"\b(annotate|underline|circle|highlight|box)\b"
        r".{0,40}\b(text|document|words?|terms?|evidence)\b", re.I)),
    ("guided notes blanks", re.compile(r"_{4,}", re.M)),
    ("primary-source excerpts", re.compile(r"\b(excerpt|source\s*[:#]|adapted from)\b", re.I)),
    ("maps/geography supports", re.compile(r"\b(map|label the|geographic context)\b", re.I)),
]

_QUESTION_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("multiple choice", re.compile(r"^\s*[(]?[a-dA-D][).]\s+\S", re.M)),
    ("stimulus-based MC", re.compile(
        r"\b(base[d]? (?:your answer )?on the (?:document|passage|map|cartoon)|stimulus)\b", re.I)),
    ("constructed response (CRQ)", re.compile(r"\b(crq|constructed[\s-]?response)\b", re.I)),
    ("short answer", re.compile(
        r"\b(in (?:1-2|one or two|a few) (?:complete )?sentences"
        r"|explain (?:why|how)|describe one)\b", re.I)),
    ("essay / enduring issues", re.compile(r"\b(essay|enduring issue|thematic essay|dbq)\b", re.I)),
    ("T-chart / compare", re.compile(r"\b(t[\s-]?chart|compare and contrast|causes and effects)\b", re.I)),
    ("film/video questions", re.compile(r"\b(film questions?|video questions?)\b", re.I)),
]

_POINTS_RE = re.compile(r"\b(\d{1,3})\s*(?:points?|pts?)\b", re.I)
_RUBRIC_RE = re.compile(
    r"^[^\n]{0,80}\b(rubric|criteria|score of \d|full credit|partial credit"
    r"|exemplary|proficient|developing)\b[^\n]{0,120}",
    re.I | re.M,
)
# Answer-key letter sequences like "1. B  2) D  3. A" — used for the
# MC letter-balance note (e.g. "no runs of 3+ same letter").
_KEY_LETTER_RE = re.compile(r"^\s*\d{1,2}\s*[).:-]\s*[(]?([A-D])[)]?\s*$", re.M)

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+[\s\n]")
_WORD_RE = re.compile(r"[A-Za-z']+")


def detect_sections(text: str) -> list[tuple[str, float]]:
    """Return (section_name, relative_position 0..1) for sections present."""
    found: list[tuple[str, float]] = []
    n = max(1, len(text))
    for name, pattern in SECTION_PATTERNS:
        m = pattern.search(text)
        if m:
            found.append((name, m.start() / n))
    return found


def sentence_stats(text: str) -> tuple[float, int]:
    """Return (avg words per sentence, sentence count) over prose-ish lines."""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    lengths = []
    for s in sentences:
        words = _WORD_RE.findall(s)
        if 1 <= len(words) <= 80:  # skip tables/garbage
            lengths.append(len(words))
    if not lengths:
        return 0.0, 0
    return statistics.mean(lengths), len(lengths)


def detect_scaffolds(text: str) -> list[str]:
    return [name for name, p in _SCAFFOLD_PATTERNS if p.search(text)]


def detect_question_types(text: str) -> list[str]:
    found = []
    for name, p in _QUESTION_TYPE_PATTERNS:
        if name == "multiple choice":
            # require several choice rows, not one stray "a) "
            if len(p.findall(text)) >= 3:
                found.append(name)
        elif p.search(text):
            found.append(name)
    return found


def detect_point_values(text: str) -> list[str]:
    return [m.group(1) for m in _POINTS_RE.finditer(text)]


def detect_rubric_lines(text: str) -> list[str]:
    return [m.group(0).strip() for m in _RUBRIC_RE.finditer(text)][:5]


def detect_key_letters(text: str) -> list[str]:
    return _KEY_LETTER_RE.findall(text)


def longest_letter_run(letters: list[str]) -> int:
    best = run = 0
    prev = None
    for letter in letters:
        run = run + 1 if letter == prev else 1
        prev = letter
        best = max(best, run)
    return best


def is_answer_key_doc(title: str, text: str) -> bool:
    blob = f"{title}\n{text[:2000]}"
    return bool(re.search(
        r"\b(answer key|answers|teacher copy|teacher version|exemplar|key)\b",
        blob, re.I,
    ))


def _excerpt_after(text: str, pattern: re.Pattern[str], chars: int = _EXEMPLAR_CHARS) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    snippet = text[m.start(): m.start() + chars].strip()
    return re.sub(r"\n{3,}", "\n\n", snippet)


# Where deterministic exemplar excerpts come from (category → trigger).
_EXEMPLAR_CATEGORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("do_now", re.compile(r"\bdo[\s-]?now\b", re.I)),
    ("directions", re.compile(r"^\s*directions?\s*[:.]", re.I | re.M)),
    ("assessment_question", re.compile(
        r"\b(in (?:1-2|one or two|a few) (?:complete )?sentences|"
        r"according to (?:this|the) document|explain (?:why|how))\b", re.I)),
]


def analyze_file_heuristics(title: str, text: str) -> dict[str, Any]:
    """Deterministic per-file analysis — works fully offline."""
    sections = detect_sections(text)
    avg_len, n_sentences = sentence_stats(text)
    return {
        "title": title,
        "sections": sections,
        "avg_sentence_words": round(avg_len, 1),
        "sentence_count": n_sentences,
        "scaffolds": detect_scaffolds(text),
        "question_types": detect_question_types(text),
        "point_values": detect_point_values(text),
        "rubric_lines": detect_rubric_lines(text),
        "key_letters": detect_key_letters(text),
        "is_answer_key": is_answer_key_doc(title, text),
    }


# ── LLM map step (cached per file) ───────────────────────────────────

_FILE_ANALYSIS_SYSTEM = (
    "You analyze one teaching document and report the teacher's writing "
    "style as compact JSON. Be concrete and literal — describe what is on "
    "the page, not what a generic teacher might do. Respond ONLY with JSON."
)

_FILE_ANALYSIS_PROMPT = """Analyze this excerpt of a teacher's classroom document.

Filename: {filename}

--- DOCUMENT EXCERPT ---
{excerpt}
--- END EXCERPT ---

Return JSON exactly like:
{{
  "tone": "<one of: direct, ornate, warm, formal, playful, neutral>",
  "register": "<short phrase, e.g. 'plain classroom language'>",
  "person": "<how the teacher addresses students, e.g. 'second person (you)'>",
  "conventions": ["<up to 4 concrete formatting/voice conventions you can SEE, \
e.g. 'numbered directions in bold', 'questions end with point values'>"],
  "snippet": "<one verbatim sentence or heading from the excerpt that best shows the teacher's voice>"
}}"""


async def analyze_file_llm(
    llm: _SupportsGenerateJSON, title: str, text: str,
) -> dict[str, Any] | None:
    """One LLM pass over a single file excerpt. Returns None on any failure."""
    excerpt = text[:_LLM_EXCERPT_CHARS]
    try:
        raw = await llm.generate_json(
            _FILE_ANALYSIS_PROMPT.format(filename=title, excerpt=excerpt),
            system=_FILE_ANALYSIS_SYSTEM,
            temperature=0.2,
            max_tokens=600,
            demo_hint="style_file_analysis",
        )
        if not isinstance(raw, dict):
            return None
        return {
            "tone": str(raw.get("tone", ""))[:40],
            "register": str(raw.get("register", ""))[:80],
            "person": str(raw.get("person", ""))[:80],
            "conventions": [str(c)[:120] for c in (raw.get("conventions") or [])][:4],
            "snippet": str(raw.get("snippet", ""))[:300],
        }
    except Exception as exc:
        logger.debug("Per-file style LLM analysis failed for %s: %s", title, exc)
        return None


# ── Reduce: aggregate + profile assembly ─────────────────────────────


def _majority(values: list[str]) -> str:
    cleaned = [v.strip().lower() for v in values if v and v.strip()]
    if not cleaned:
        return ""
    return Counter(cleaned).most_common(1)[0][0]


def _sentence_style_label(avg: float) -> str:
    if avg <= 0:
        return ""
    if avg < 12:
        return f"short, direct sentences (avg {avg:.0f} words)"
    if avg < 20:
        return f"medium-length sentences (avg {avg:.0f} words)"
    return f"long, elaborate sentences (avg {avg:.0f} words)"


_REDUCE_SYSTEM = (
    "You summarize a teacher's writing style from aggregate statistics and "
    "real excerpts of their classroom materials. Write plainly and "
    "concretely, in second person ('Your lessons…'). Respond ONLY with JSON."
)

_REDUCE_PROMPT = """Here is what was measured across {n_files} of a teacher's own classroom files.

Detected lesson sections (share of files containing each, in typical order):
{structure}

Voice signals: tone={tone}, register={register}, person={person}, {sentence_style}
Question types seen: {question_types}
Scaffolds seen: {scaffolds}
Conventions noted: {conventions}

Real excerpts from their files:
{snippets}

Return JSON exactly like:
{{
  "voice_description": "<2-3 sentences describing this teacher's writing voice, \
addressed to the teacher ('Your materials...'). Concrete, no flattery.>",
  "structure_summary": "<1-2 sentences: how a typical lesson of theirs flows, \
e.g. 'Your lessons usually open with a Do-Now, ...'>",
  "vocabulary_level": "<one of: elementary, grade_appropriate, academic>"
}}"""


def _fallback_voice_description(profile: StyleProfile) -> str:
    bits = []
    if profile.voice_tone:
        bits.append(f"{profile.voice_tone} in tone")
    if profile.sentence_style:
        bits.append(profile.sentence_style)
    if profile.voice_register:
        bits.append(profile.voice_register)
    if not bits:
        return "Voice analysis pending — structure and conventions below were detected from your files."
    return "Your materials read " + ", ".join(bits) + "."


def _fallback_structure_summary(sections: list[SectionPattern]) -> str:
    common = [s.name for s in sections if s.frequency >= 0.25 and s.name != "Answer Key"]
    if not common:
        return ""
    return "Your lessons usually flow: " + " → ".join(common[:6]) + "."


async def build_profile(
    docs: list[Any],
    *,
    name: str,
    source_path: str,
    llm: _SupportsGenerateJSON | None = None,
    files_skipped: int = 0,
    progress_callback: Any = None,
) -> StyleProfile:
    """Map/reduce a corpus of ingested Documents into a StyleProfile.

    ``docs`` are ``clawed.models.Document`` (title/content/source_path).
    Deterministic structure; the LLM fills qualitative fields when
    available. Per-file LLM analyses are cached by content hash, so
    re-ingesting a folder is incremental.
    """
    now = datetime.now(UTC).isoformat(timespec="seconds")
    profile_id = slugify(name)
    profile = StyleProfile(
        profile_id=profile_id,
        name=name,
        source_path=source_path,
        created_at=now,
        updated_at=now,
        files_analyzed=len(docs),
        files_skipped=files_skipped,
    )

    def _progress(msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    # ── Map: heuristics on every file; LLM on a budgeted subset ──────
    section_hits: Counter[str] = Counter()
    section_positions: dict[str, list[float]] = {}
    lessonish_docs = 0
    sentence_avgs: list[float] = []
    scaffold_hits: Counter[str] = Counter()
    qtype_hits: Counter[str] = Counter()
    point_values: Counter[str] = Counter()
    rubric_lines: list[str] = []
    key_letters: list[str] = []
    answer_key_docs = 0
    llm_tones: list[str] = []
    llm_registers: list[str] = []
    llm_persons: list[str] = []
    llm_conventions: Counter[str] = Counter()
    llm_snippets: list[StyleExemplar] = []
    llm_budget = _MAX_LLM_FILES

    exemplar_pool: dict[str, StyleExemplar] = {}

    for i, doc in enumerate(docs):
        text = (doc.content or "")
        title = doc.title or Path(doc.source_path or "file").name
        if len(text.strip()) < 40:
            continue
        h = analyze_file_heuristics(title, text)

        if h["sections"]:
            lessonish_docs += 1
            for sec_name, pos in h["sections"]:
                section_hits[sec_name] += 1
                section_positions.setdefault(sec_name, []).append(pos)
        if h["avg_sentence_words"]:
            sentence_avgs.append(h["avg_sentence_words"])
        for s in h["scaffolds"]:
            scaffold_hits[s] += 1
        for q in h["question_types"]:
            qtype_hits[q] += 1
        for p in h["point_values"]:
            point_values[p] += 1
        rubric_lines.extend(h["rubric_lines"])
        key_letters.extend(h["key_letters"])
        if h["is_answer_key"]:
            answer_key_docs += 1

        # Deterministic exemplars: first good excerpt per category.
        for category, pattern in _EXEMPLAR_CATEGORY_PATTERNS:
            if category not in exemplar_pool:
                snippet = _excerpt_after(text, pattern)
                if len(snippet) > 60:
                    exemplar_pool[category] = StyleExemplar(
                        category=category, source=title, snippet=snippet,
                    )

        # LLM map (cache first, then budget)
        analysis = None
        content_hash = _content_hash(text[:_LLM_EXCERPT_CHARS])
        cached = cache_get(content_hash)
        if cached is not None:
            analysis = cached
        elif llm is not None and llm_budget > 0:
            llm_budget -= 1
            _progress(f"Reading your style — file {i + 1}/{len(docs)}: {title}")
            analysis = await analyze_file_llm(llm, title, text)
            if analysis is not None:
                cache_put(content_hash, analysis)
        if analysis:
            if analysis.get("tone"):
                llm_tones.append(analysis["tone"])
            if analysis.get("register"):
                llm_registers.append(analysis["register"])
            if analysis.get("person"):
                llm_persons.append(analysis["person"])
            for c in analysis.get("conventions", []):
                llm_conventions[c] += 1
            snippet = (analysis.get("snippet") or "").strip()
            if len(snippet) > 25 and len(llm_snippets) < _MAX_EXEMPLARS:
                llm_snippets.append(StyleExemplar(
                    category="voice", source=title, snippet=snippet[:300],
                ))

    # ── Reduce: deterministic aggregation ────────────────────────────
    denom = max(1, lessonish_docs)
    structure = [
        SectionPattern(
            name=sec_name,
            count=count,
            frequency=round(count / denom, 2),
            avg_position=round(statistics.mean(section_positions[sec_name]), 3),
        )
        for sec_name, count in section_hits.items()
    ]
    structure.sort(key=lambda s: s.avg_position)
    profile.lesson_structure = structure

    avg_sentence = statistics.mean(sentence_avgs) if sentence_avgs else 0.0
    profile.sentence_style = _sentence_style_label(avg_sentence)
    profile.voice_tone = _majority(llm_tones) or (
        "direct" if 0 < avg_sentence < 13 else ""
    )
    profile.voice_register = _majority(llm_registers)
    profile.voice_person = _majority(llm_persons)

    profile.scaffolds = [s for s, _ in scaffold_hits.most_common(6)]
    profile.question_types = [q for q, _ in qtype_hits.most_common(6)]
    profile.point_values = [
        f"{points} pts" for points, _ in point_values.most_common(4)
    ]
    profile.rubric_language = list(dict.fromkeys(rubric_lines))[:4]
    profile.formatting = [c for c, _ in llm_conventions.most_common(6)]

    if answer_key_docs:
        share = answer_key_docs / max(1, len(docs))
        profile.answer_key_style = (
            f"Separate teacher answer keys / exemplars ship alongside student "
            f"materials ({answer_key_docs} key docs, {share:.0%} of files)."
        )
    if key_letters:
        run = longest_letter_run(key_letters)
        dist = Counter(key_letters)
        dist_str = " ".join(f"{letter}:{n}" for letter, n in sorted(dist.items()))
        profile.mc_letter_note = (
            f"MC answer keys balance letters ({dist_str}); "
            f"longest same-letter run = {run}"
            + (" — avoid runs of 3+." if run <= 2 else ".")
        )

    profile.exemplars = list(exemplar_pool.values()) + llm_snippets
    profile.exemplars = profile.exemplars[:_MAX_EXEMPLARS]

    # ── Reduce: one LLM call writes the readable summaries ───────────
    reduced = None
    if llm is not None:
        structure_lines = "\n".join(
            f"- {s.name}: {s.frequency:.0%} of lessons"
            for s in structure if s.count >= 2
        ) or "- (no recurring sections detected)"
        snippets_text = "\n".join(
            f"[{e.source}] {e.snippet[:220]}" for e in profile.exemplars[:5]
        ) or "(none)"
        prompt = _REDUCE_PROMPT.format(
            n_files=len(docs),
            structure=structure_lines,
            tone=profile.voice_tone or "unknown",
            register=profile.voice_register or "unknown",
            person=profile.voice_person or "unknown",
            sentence_style=profile.sentence_style or "sentence length unknown",
            question_types=", ".join(profile.question_types) or "unknown",
            scaffolds=", ".join(profile.scaffolds) or "none detected",
            conventions="; ".join(profile.formatting) or "none noted",
            snippets=snippets_text,
        )
        try:
            _progress("Writing your style profile…")
            reduced = await llm.generate_json(
                prompt, system=_REDUCE_SYSTEM, temperature=0.3,
                max_tokens=700, demo_hint="style_profile_reduce",
            )
        except Exception as exc:
            logger.debug("Style reduce LLM call failed: %s", exc)

    if isinstance(reduced, dict):
        profile.voice_description = str(reduced.get("voice_description", ""))[:600]
        profile.structure_summary = str(reduced.get("structure_summary", ""))[:400]
        profile.vocabulary_level = str(reduced.get("vocabulary_level", ""))[:40]
    if not profile.voice_description:
        profile.voice_description = _fallback_voice_description(profile)
    if not profile.structure_summary:
        profile.structure_summary = _fallback_structure_summary(structure)
    if not profile.vocabulary_level:
        profile.vocabulary_level = "grade_appropriate"

    return profile


# ── Consumption: system-prompt injection ────────────────────────────


def prompt_block(profile: StyleProfile) -> str:
    """The system-prompt section that conditions generation on this teacher."""
    lines: list[str] = [
        f"## ACTIVE STYLE PROFILE — \"{profile.name}\" (learned from this teacher's own files)",
        "Everything you produce MUST match this teacher's real voice, "
        "structure, and conventions — not a generic style:",
    ]
    if profile.voice_description:
        lines.append(f"- Voice: {profile.voice_description}")
    if profile.sentence_style and profile.sentence_style not in profile.voice_description:
        lines.append(f"- Sentences: {profile.sentence_style}")
    if profile.structure_summary:
        lines.append(f"- Lesson flow: {profile.structure_summary}")
    common = [
        f"{s.name} ({s.frequency:.0%})" for s in profile.lesson_structure
        if s.frequency >= 0.2 and s.name != "Answer Key"
    ]
    if common:
        lines.append(f"- Recurring sections: {', '.join(common[:8])}")
    if profile.question_types:
        lines.append(f"- Assessment style: {', '.join(profile.question_types[:5])}")
    if profile.point_values:
        lines.append(f"- Point values they use: {', '.join(profile.point_values)}")
    if profile.answer_key_style:
        lines.append(f"- Answer keys: {profile.answer_key_style} Always produce the "
                     "teacher key as a SEPARATE document, never on the student copy.")
    if profile.mc_letter_note:
        lines.append(f"- MC balance: {profile.mc_letter_note}")
    if profile.scaffolds:
        lines.append(f"- Scaffolds they reach for: {', '.join(profile.scaffolds[:6])}")
    if profile.formatting:
        lines.append(f"- Formatting habits: {'; '.join(profile.formatting[:5])}")
    if profile.vocabulary_level:
        lines.append(f"- Vocabulary level: {profile.vocabulary_level}")
    if profile.exemplars:
        lines.append("\nReal excerpts from their files — imitate this register exactly:")
        for e in profile.exemplars[:4]:
            snippet = e.snippet.replace("\n", " ")[:260]
            lines.append(f'  • ({e.category}) "{snippet}"')
    return "\n".join(lines)


def active_prompt_block() -> str:
    """Prompt block for the active profile, or '' when using default style."""
    try:
        profile = get_active_profile()
    except Exception as exc:  # never break generation over a profile read
        logger.debug("Active style profile load failed: %s", exc)
        return ""
    if profile is None:
        return ""
    return prompt_block(profile)
