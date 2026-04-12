"""Reading report — analyze ingested documents and summarize what we learned.

Produces a report that feels like a colleague sharing observations, not a
database query.  Phase 1 of the quality layer adds an LLM pass that reads
actual excerpts and returns qualitative observations a regex can never make.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clawed.models import AppConfig, Document, TeacherPersona

log = logging.getLogger(__name__)


def generate_reading_report(
    documents: list[Document],
    persona: TeacherPersona | None = None,
) -> dict[str, Any]:
    """Analyze ingested documents and produce a structured reading report.

    Returns a dict with keys:
        teacher_details, signature_moves, topic_coverage, strengths,
        gaps, favorite_strategies, voice_patterns, assessment_patterns,
        interesting_finds, doc_stats.
    """
    report: dict[str, Any] = {
        "teacher_details": {},
        "signature_moves": [],
        "topic_coverage": {},
        "strengths": [],
        "gaps": [],
        "favorite_strategies": [],
        "voice_patterns": [],
        "assessment_patterns": [],
        "interesting_finds": [],
        "doc_stats": {},
        "llm_observations": None,     # None = not yet run, [] = ran but empty
        "_excerpts_for_llm": [],       # populated for async LLM pass
    }

    if not documents:
        return report

    # Aggregate all text for analysis
    all_text = "\n".join(doc.content for doc in documents if doc.content)

    # ── Document stats ───────────────────────────────────────────────
    type_counts: Counter[str] = Counter()
    for doc in documents:
        ext = doc.doc_type.value.upper() if doc.doc_type else "UNKNOWN"
        type_counts[ext] += 1

    report["doc_stats"] = {
        "total": len(documents),
        "by_type": dict(type_counts.most_common()),
    }

    # ── Teacher name detection (headers/footers only) ──────────────────
    # Only look in document headers/footers to avoid matching historical
    # figures in content (e.g., "Dr. King" from MLK lessons)
    historical_surnames = {
        "King", "Lincoln", "Washington", "Jefferson", "Roosevelt", "Kennedy",
        "Obama", "Trump", "Gandhi", "Churchill", "Hitler", "Napoleon",
        "Caesar", "Alexander", "Columbus", "Martin", "Luther", "Franklin",
        "Adams", "Hamilton", "Madison", "Monroe", "Jackson", "Grant", "Lee",
        "Sherman", "Douglass", "Tubman", "Parks", "Malcolm", "Mandela",
    }

    _title_name = r"((?:Mr\.|Ms\.|Mrs\.|Dr\.)[ ]+[A-Z][a-z]+(?:[ ]+[A-Z][a-z]+)?)"
    header_name_patterns = [
        re.compile(
            r"(?:Teacher|By|Prepared by|Created by)[:\s]+" + _title_name,
            re.IGNORECASE,
        ),
        re.compile(r"^" + _title_name + r"\s*[-—|]"),
        re.compile(
            _title_name + r"(?:'s)?\s+(?:Class|Period|Lesson|Grade)",
            re.IGNORECASE,
        ),
    ]

    header_name_counter: Counter[str] = Counter()
    for doc in documents:
        lines = doc.content.split("\n")
        # Only check first 5 and last 5 lines of each document
        header_lines = lines[:5] + lines[-5:]
        header_text = "\n".join(header_lines)
        for pattern in header_name_patterns:
            matches = pattern.findall(header_text)
            for name in matches:
                surname = name.split()[-1] if name else ""
                if surname not in historical_surnames:
                    header_name_counter[name] += 1

    # Fallback: general name pattern in headers only (not body text)
    if not header_name_counter:
        general_name = re.compile(r"\b(Mr\.|Ms\.|Mrs\.|Dr\.)[ ]+([A-Z][a-z]+(?:[ ]+[A-Z][a-z]+)?)\b")
        for doc in documents:
            lines = doc.content.split("\n")
            header_text = "\n".join(lines[:5] + lines[-5:])
            for prefix, name in general_name.findall(header_text):
                surname = name.split()[-1]
                if surname not in historical_surnames:
                    header_name_counter[f"{prefix} {name}"] += 1

    if header_name_counter:
        most_common_name, name_count = header_name_counter.most_common(1)[0]
        report["teacher_details"]["name_used"] = most_common_name
        report["teacher_details"]["name_occurrences"] = name_count

    # School name detection
    school_pattern = re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
        r"(?:Middle|High|Elementary|Academy|School|Prep|Charter))"
        r"(?:\s+School)?\b"
    )
    school_matches = school_pattern.findall(all_text)
    if school_matches:
        school_counter: Counter[str] = Counter()
        for s in school_matches:
            school_counter[s] += 1
        report["teacher_details"]["school"] = school_counter.most_common(1)[0][0]

    # ── Voice patterns ───────────────────────────────────────────────
    # Opening phrases from Do Now / Warm-Up sections
    do_now_pattern = re.compile(
        r"(?:Do Now|Warm[- ]?Up|Bell ?Ringer)[:\s]*([^\n]{10,80})",
        re.IGNORECASE,
    )
    openers = do_now_pattern.findall(all_text)

    teacher_greeting_starters = {
        "alright", "friends", "ok", "okay", "good morning", "good afternoon",
        "scholars", "today", "let's", "welcome", "take out", "turn to",
        "historians", "scientists", "mathematicians", "class", "everyone",
        "hey", "hello", "hi", "team",
    }

    if openers:
        filtered_openers = []
        for opener in openers:
            first_words = opener.strip().lower().split()[:3]
            first_phrase = " ".join(first_words)
            if any(first_phrase.startswith(starter) for starter in teacher_greeting_starters):
                filtered_openers.append(opener)
        openers = filtered_openers

    if openers:
        unique_openers = list(dict.fromkeys(openers[:10]))
        report["voice_patterns"].append(
            f"Often opens with: '{unique_openers[0].strip()}'"
        )

    # Address terms
    address_terms = {
        "friends": r"\bfriends\b",
        "scholars": r"\bscholars\b",
        "historians": r"\bhistorians\b",
        "scientists": r"\bscientists\b",
        "mathematicians": r"\bmathematicians\b",
        "students": r"\bstudents\b",
        "class": r"\bclass\b",
        "team": r"\bteam\b",
        "everybody": r"\beverybody\b",
        "everyone": r"\beveryone\b",
    }
    for term, pattern in address_terms.items():
        count = len(re.findall(pattern, all_text, re.IGNORECASE))
        if count >= 3:
            report["voice_patterns"].append(
                f"Calls students '{term}' ({count} times across your files)"
            )

    # ── Topic coverage ───────────────────────────────────────────────
    topics = {
        "American Revolution": r"American Revolution|Revolutionary War|1776|Declaration of Independence",
        "Civil War": r"Civil War|Gettysburg|Emancipation|Antebellum",
        "Constitution": r"Constitution|Bill of Rights|Amendments|Federalist",
        "WWI": r"World War I|WWI|Great War|Trench Warfare",
        "WWII": r"World War II|WWII|Holocaust|Pearl Harbor|D-Day",
        "Reconstruction": r"Reconstruction|Freedmen|Jim Crow|13th Amendment|14th Amendment|15th Amendment",
        "Immigration": r"Immigration|Ellis Island|Immigrants|Nativism",
        "Women's Suffrage": r"Women's Suffrage|19th Amendment|Seneca Falls|Susan B\. Anthony",
        "Civil Rights": r"Civil Rights|MLK|Martin Luther King|Brown v\. Board|Rosa Parks|Segregation",
        "Cold War": r"Cold War|Soviet|Cuban Missile|McCarthyism|Iron Curtain",
        "Industrialization": r"Industrialization|Industrial Revolution|Gilded Age|Robber Barons",
    }
    topic_counts: dict[str, int] = {}
    for topic, pattern in topics.items():
        count = len(re.findall(pattern, all_text, re.IGNORECASE))
        if count > 0:
            topic_counts[topic] = count

    report["topic_coverage"] = dict(
        sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    )

    # Guess primary subject from topic coverage
    if topic_counts:
        report["teacher_details"]["subject_guess"] = "Social Studies"
    # Future: detect Science, Math, ELA from their respective topic patterns

    # Strengths = topics with significant coverage
    if topic_counts:
        sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        report["strengths"] = [t[0] for t in sorted_topics[:5] if t[1] >= 3]

    # Gaps = topics with zero or near-zero coverage
    all_topics = set(topics.keys())
    covered = {t for t, c in topic_counts.items() if c >= 2}
    report["gaps"] = sorted(all_topics - covered)

    # ── Activity strategies ──────────────────────────────────────────
    strategies = {
        "Jigsaw": r"\bjigsaw\b",
        "DBQ": r"\bDBQ\b|Document[- ]Based Question",
        "Socratic Seminar": r"Socratic Seminar",
        "Think-Pair-Share": r"Think[- ]Pair[- ]Share",
        "Gallery Walk": r"Gallery Walk",
        "Debate": r"\bdebate\b",
        "Station Rotation": r"Station Rotation|Stations\b",
        "Primary Source Analysis": r"Primary Source|primary source",
    }
    strategy_counts: dict[str, int] = {}
    for strategy, pattern in strategies.items():
        count = len(re.findall(pattern, all_text, re.IGNORECASE))
        if count > 0:
            strategy_counts[strategy] = count

    report["favorite_strategies"] = [
        f"{s} ({c}x)"
        for s, c in sorted(strategy_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # ── Assessment patterns ──────────────────────────────────────────
    exit_ticket_count = len(
        re.findall(r"Exit Ticket|exit ticket", all_text, re.IGNORECASE)
    )
    if exit_ticket_count:
        report["assessment_patterns"].append(
            f"Uses exit tickets ({exit_ticket_count} found)"
        )

    question_count = len(re.findall(r"\?\s", all_text))
    if question_count:
        report["assessment_patterns"].append(
            f"~{question_count} questions across all documents"
        )

    # ── Structural patterns (signature moves) ────────────────────────
    structural = {
        "AIM": r"\bAIM\b[:\s]",
        "Do Now": r"Do Now",
        "SWBAT": r"SWBAT|Students Will Be Able To",
        "Essential Question": r"Essential Question|EQ[:\s]",
    }
    for name, pattern in structural.items():
        count = len(re.findall(pattern, all_text, re.IGNORECASE))
        if count >= 2:
            report["signature_moves"].append(f"Uses {name} structure ({count}x)")

    # ── Interesting finds ────────────────────────────────────────────
    if report["doc_stats"]["total"] > 100:
        report["interesting_finds"].append(
            f"That's a LOT of materials — {report['doc_stats']['total']} files. "
            "You've clearly been at this a while."
        )

    if persona and persona.name and persona.name != "My Teaching Persona":
        if report["teacher_details"].get("name_used"):
            detected = report["teacher_details"]["name_used"]
            if detected.split()[-1] != persona.name.split()[-1]:
                report["interesting_finds"].append(
                    f"Your files reference {detected} — is that you, or a co-teacher?"
                )

    # ── Prepare excerpts for the async LLM pass ──────────────────────
    report["_excerpts_for_llm"] = _select_representative_excerpts(documents)

    return report


# ── LLM-enhanced observation helpers ──────────────────────────────────


def _select_representative_excerpts(
    documents: list[Document],
    max_excerpts: int = 8,
) -> list[Document]:
    """Pick a diverse subset of documents for the LLM to read.

    Uses round-robin across doc types so the LLM sees a variety of
    formats, then fills remaining slots with documents that have the
    most content (likely the richest lesson plans).
    """
    if not documents:
        return []

    if len(documents) <= max_excerpts:
        return list(documents)

    # Group documents by doc type
    by_type: dict[str, list[Document]] = {}
    for doc in documents:
        key = doc.doc_type.value if doc.doc_type else "unknown"
        by_type.setdefault(key, []).append(doc)

    # Sort each group by content length descending (richest first)
    for group in by_type.values():
        group.sort(key=lambda d: len(d.content or ""), reverse=True)

    # Round-robin across types
    selected: list[Document] = []
    seen_ids: set[int] = set()
    type_keys = sorted(by_type.keys())
    idx = 0
    while len(selected) < max_excerpts:
        added_this_round = False
        for key in type_keys:
            group = by_type[key]
            if idx < len(group) and len(selected) < max_excerpts:
                doc = group[idx]
                if id(doc) not in seen_ids:
                    selected.append(doc)
                    seen_ids.add(id(doc))
                    added_this_round = True
        idx += 1
        if not added_this_round:
            break

    return selected


def _build_llm_reading_prompt(
    regex_report: dict[str, Any],
    excerpts: list[Document],
) -> str:
    """Build the user prompt for the LLM reading-observations call.

    Includes the regex-derived stats so the LLM can reference them,
    plus the actual document excerpts for qualitative analysis.
    """
    stats = regex_report.get("doc_stats", {})
    total = stats.get("total", 0)
    by_type = stats.get("by_type", {})
    type_str = ", ".join(f"{c} {t}" for t, c in by_type.items()) if by_type else "unknown mix"

    topics = regex_report.get("topic_coverage", {})
    topic_str = ", ".join(
        f"{t} ({c})" for t, c in list(topics.items())[:8]
    ) if topics else "none detected"

    strategies = regex_report.get("favorite_strategies", [])
    strategy_str = ", ".join(strategies[:5]) if strategies else "none detected"

    strengths = regex_report.get("strengths", [])
    strength_str = ", ".join(strengths) if strengths else "none"

    gaps = regex_report.get("gaps", [])
    gap_str = ", ".join(gaps[:5]) if gaps else "none"

    # Build excerpt text blocks
    excerpt_blocks = []
    for i, doc in enumerate(excerpts, 1):
        doc_type = doc.doc_type.value.upper() if doc.doc_type else "UNKNOWN"
        title = doc.title or "Untitled"
        # Truncate very long documents to keep prompt reasonable
        content = (doc.content or "")[:1500]
        if len(doc.content or "") > 1500:
            content += "\n[... truncated ...]"
        excerpt_blocks.append(
            f"--- Excerpt {i}: \"{title}\" ({doc_type}) ---\n{content}"
        )

    excerpts_text = "\n\n".join(excerpt_blocks)

    return (
        f"A teacher has uploaded {total} curriculum files ({type_str}).\n\n"
        f"REGEX ANALYSIS SUMMARY:\n"
        f"- Topic coverage: {topic_str}\n"
        f"- Strongest areas: {strength_str}\n"
        f"- Gaps: {gap_str}\n"
        f"- Strategies used: {strategy_str}\n\n"
        f"Below are {len(excerpts)} representative excerpts from their files. "
        f"Read them carefully and share 3-5 genuine qualitative observations "
        f"that a regex analysis could never produce. Focus on:\n"
        f"- How the teacher's instructional style comes through\n"
        f"- The quality and sophistication of their activities\n"
        f"- What their Do Nows actually look like\n"
        f"- Whether assessments align with instruction\n"
        f"- Anything genuinely surprising or distinctive about their practice\n"
        f"- How their pedagogical approach has evolved (if visible)\n\n"
        f"Respond ONLY with a JSON array of observation strings. "
        f"Each observation should be 1-2 sentences, specific and grounded "
        f"in what you actually read — not generic praise.\n\n"
        f"{excerpts_text}"
    )


_LLM_SYSTEM = (
    "You are an expert instructional coach analyzing a teacher's curriculum "
    "materials. Respond only with a JSON array of observation strings."
)


async def enhance_reading_report_with_llm(
    report: dict[str, Any],
    config: AppConfig | None = None,
) -> None:
    """Add qualitative LLM observations to an existing reading report.

    Reads the excerpts stored in ``report["_excerpts_for_llm"]`` by
    :func:`generate_reading_report`, sends them to the LLM, and stores
    the result in ``report["llm_observations"]``.

    Wrapped in try/except so the report still works if the LLM call
    fails — it just falls back to the regex-only version.
    """
    excerpts = report.get("_excerpts_for_llm", [])
    if not excerpts:
        # Nothing to send to the LLM — leave llm_observations as None
        return

    try:
        from clawed.llm import LLMClient

        client = LLMClient(config)
        prompt = _build_llm_reading_prompt(report, excerpts)
        result = await client.generate_json(
            prompt=prompt,
            system=_LLM_SYSTEM,
            temperature=0.4,
            max_tokens=800,
        )

        # Validate: must be a list of strings
        if isinstance(result, list) and all(isinstance(s, str) for s in result):
            report["llm_observations"] = result
        else:
            log.warning(
                "LLM returned unexpected format for reading observations: %s",
                type(result).__name__,
            )
            report["llm_observations"] = []

    except Exception:
        log.exception("LLM reading-report enhancement failed; using regex-only report")
        report["llm_observations"] = []


def format_reading_report(report: dict[str, Any]) -> str:
    """Format the reading report as natural conversational text.

    Should feel like a colleague sharing observations, not a database query.
    """
    if not report or not report.get("doc_stats", {}).get("total"):
        return "I haven't read any of your files yet."

    lines: list[str] = []
    stats = report["doc_stats"]

    # File stats
    type_breakdown = ", ".join(
        f"{count} {ext}" for ext, count in stats.get("by_type", {}).items()
    )
    lines.append(
        f"I read through {stats['total']} files"
        + (f" ({type_breakdown})" if type_breakdown else "")
        + "."
    )

    # Teacher name
    teacher_name = report.get("teacher_details", {}).get("name_used")
    if teacher_name:
        lines.append(f"Your students know you as {teacher_name}.")

    # School
    school = report.get("teacher_details", {}).get("school")
    if school:
        lines.append(f"Looks like you're at {school}.")

    # Voice patterns
    if report.get("voice_patterns"):
        lines.append("")
        lines.append("A few things I noticed about your voice:")
        for vp in report["voice_patterns"][:5]:
            lines.append(f"- {vp}")

    # Signature moves
    if report.get("signature_moves"):
        lines.append("")
        lines.append("Your lesson structure:")
        for sm in report["signature_moves"][:5]:
            lines.append(f"- {sm}")

    # Topic coverage
    if report.get("strengths"):
        lines.append("")
        lines.append(
            "Your strongest coverage is in "
            + ", ".join(report["strengths"])
            + "."
        )

    # Strategies
    if report.get("favorite_strategies"):
        lines.append("")
        lines.append(
            "Your go-to strategies: "
            + ", ".join(report["favorite_strategies"][:5])
            + "."
        )

    # Assessment patterns
    if report.get("assessment_patterns"):
        lines.append("")
        for ap in report["assessment_patterns"]:
            lines.append(f"- {ap}")

    # Gaps
    if report.get("gaps"):
        lines.append("")
        lines.append(
            "I didn't find much on "
            + ", ".join(report["gaps"][:5])
            + " — is that covered in a different quarter?"
        )

    # Interesting finds
    if report.get("interesting_finds"):
        lines.append("")
        for find in report["interesting_finds"]:
            lines.append(find)

    # ── LLM qualitative observations ──────────────────────────────
    if report.get("llm_observations"):
        lines.append("")
        lines.append("Here's what stood out to me after reading your materials:")
        for obs in report["llm_observations"]:
            lines.append(f"- {obs}")

    return "\n".join(lines)
