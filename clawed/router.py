"""Intent router — maps teacher messages to the right handler.

This is the core of the conversational experience. A teacher should never
need to type a specific command. They just say what they want and the
router figures it out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    """What the teacher (or student) is trying to do."""

    # Setup & Config
    SETUP = "setup"
    CONNECT_DRIVE = "connect_drive"
    CONNECT_LOCAL = "connect_local"
    SHOW_STATUS = "show_status"
    SET_API_KEY = "set_api_key"

    # Generation
    GENERATE_UNIT = "generate_unit"
    GENERATE_LESSON = "generate_lesson"
    GENERATE_MATERIALS = "generate_materials"
    GENERATE_ASSESSMENT = "generate_assessment"
    GENERATE_BELLRINGER = "generate_bellringer"
    GENERATE_DIFFERENTIATION = "generate_differentiation"
    GENERATE_YEAR_MAP = "generate_year_map"
    GENERATE_PACING_GUIDE = "generate_pacing_guide"

    # Search & Research
    WEB_SEARCH = "web_search"
    SEARCH_STANDARDS = "search_standards"
    FIND_RESOURCE = "find_resource"

    # Export & Share
    EXPORT_PDF = "export_pdf"
    EXPORT_CLASSROOM = "export_classroom"
    SHARE_STUDENTS = "share_students"

    # Student bot management (teacher commands)
    START_STUDENT_BOT = "start_student_bot"
    SHOW_STUDENT_REPORT = "show_student_report"
    SET_HINT_MODE = "set_hint_mode"

    # Student mode
    STUDENT_QUESTION = "student_question"
    STUDENT_QUIZ = "student_quiz"
    STUDENT_HINT = "student_hint"

    # Additional intents (from tg.py _detect_intent)
    DEMO = "demo"
    GAP_ANALYSIS = "gap_analysis"
    SWITCH_MODEL = "switch_model"
    SCHEDULE = "schedule"
    SHOW_PERSONA = "show_persona"
    SHOW_SETTINGS = "show_settings"
    SHOW_PROGRESS = "show_progress"
    SHOW_FEEDBACK = "show_feedback"
    EXPORT_SLIDES = "export_slides"
    EXPORT_HANDOUT = "export_handout"
    EXPORT_DOC = "export_doc"

    # Conversation
    HELP = "help"
    CLARIFY = "clarify"  # We need more info
    UNKNOWN = "unknown"


@dataclass
class ParsedIntent:
    """Result of parsing a teacher message."""

    intent: Intent
    topic: str | None = None
    grade: str | None = None
    subject: str | None = None
    weeks: int | None = None
    url: str | None = None
    query: str | None = None
    format: str | None = None
    raw: str = ""


# ── Patterns for intent detection ────────────────────────────────────────────

UNIT_PATTERNS = [
    r"plan.{0,20}unit",
    r"unit plan",
    r"unit on",
    r"curriculum unit",
    r"plan.{0,20}(week|weeks)",
    r"semester plan",
    r"month.{0,10}curriculum",
]

LESSON_PATTERNS = [
    r"(generate|create|write|make|build).{0,20}lesson",
    r"lesson plan",
    r"lesson on",
    r"daily lesson",
    r"class plan",
    r"plan.{0,20}(class|tomorrow|today|monday|tuesday|wednesday|thursday|friday)",
]

MATERIALS_PATTERNS = [
    r"(make|create|generate|write).{0,20}(worksheet|handout|activity)",
    r"student worksheet",
    r"practice (problems|questions|sheet)",
    r"(make|create|generate).{0,20}(materials|resources)",
]

ASSESSMENT_PATTERNS = [
    r"(make|create|generate|write).{0,20}(test|quiz|assessment|exam)",
    r"(formative|summative) assessment",
    r"(unit|chapter) test",
    r"rubric",
    r"exit ticket",
]

SEARCH_PATTERNS = [
    r"find.{0,30}(article|story|video|resource|example)",
    r"search for",
    r"look up",
    r"current (events?|news|example)",
    r"what (is|are|does|do).{0,20}(happening|recent|news|current)",
    r"news about",
    r"example.{0,20}(real.world|current|today|recent)",
]

STANDARDS_PATTERNS = [
    r"(ngss|common core|ccss|c3|standards?).{0,30}(for|about|on)",
    r"what.{0,20}standards",
    r"standards.{0,20}(align|cover|address)",
    r"standards? for grade",
]

DRIVE_PATTERNS = [
    r"(connect|link|add|attach|use).{0,20}(drive|google drive|folder)",
    r"drive\.google\.com",
    r"docs\.google\.com",
    r"my (drive|materials|files|lessons|folder)",
    r"https?://drive\.",
]

LOCAL_PATTERNS = [
    r"(/users/|/home/|~/|c:\\|d:\\)",  # File paths
    r"(connect|use|add).{0,20}(local|folder|directory|path|files)",
    r"my (computer|desktop|documents|downloads)",
]

BELLRINGER_PATTERNS = [
    r"bell.?ringer",
    r"do.?now",
    r"warm.?up",
    r"starter",
    r"opening activity",
    r"hook",
]

YEAR_MAP_PATTERNS = [
    r"year.{0,10}(map|plan|curriculum)",
    r"full.?year.{0,10}(plan|map|curriculum)",
    r"curriculum.{0,10}map",
    r"annual.{0,10}(plan|curriculum)",
    r"yearly.{0,10}(plan|map)",
    r"scope.{0,10}(and|&).{0,10}sequence",
    r"plan.{0,10}(the|my|a).{0,10}year",
    r"plan.{0,10}(the|my|a).{0,10}full year",
]

PACING_PATTERNS = [
    r"pacing.{0,10}(guide|calendar|chart)",
    r"week.{0,5}by.{0,5}week.{0,10}(plan|schedule|calendar|pacing)",
    r"(create|generate|make|build).{0,20}pacing",
    r"calendar.{0,10}(pacing|schedule)",
]

EXPORT_PATTERNS = {
    "pdf": [r"(export|download|save).{0,20}pdf", r"pdf version", r"print"],
    "classroom": [r"google classroom", r"classroom (version|format|export)", r"import.{0,20}classroom"],
    "share": [r"share.{0,20}student", r"student (link|access|version)", r"send.{0,20}student"],
}

STATUS_PATTERNS = [
    r"(show|what('s| is)).{0,20}(status|config|settings|persona)",
    r"what do you know about me",
    r"my teaching style",
    r"/status",
]

SETUP_PATTERNS = [
    r"/setup",
    r"(set up|setup|configure|get started)",
    r"how do (i|you) (use|start|begin|connect)",
    r"(i('m| am) a|i teach|i'm a teacher)",
]

STUDENT_BOT_PATTERNS = [
    r"start\s+student\s+bot",
    r"activate\s+student\s+(bot|chat)",
    r"student\s+bot\s+for\s+lesson",
    r"open\s+student\s+(bot|chat)",
    r"launch\s+student\s+(bot|chat)",
    r"enable\s+student\s+(bot|chat)",
]

STUDENT_REPORT_PATTERNS = [
    r"(show|what).{0,20}students?.{0,20}(asking|asked|questions?)",
    r"student\s+(report|questions?|activity|analytics|insights?)",
    r"what\s+are\s+students?\s+asking",
    r"student\s+bot\s+(report|stats|status)",
]

HINT_MODE_PATTERNS = [
    r"(set|enable|turn\s+on|activate).{0,20}hint\s+mode",
    r"hint.?only\s+mode",
    r"hints?\s+(only|mode)",
    r"(disable|turn\s+off).{0,20}hint\s+mode",
    r"no\s+direct\s+answers?",
]

HELP_PATTERNS = [
    r"(help|what can you|what do you do|how does this work)",
    r"(commands|features|capabilities)",
    r"/help",
]

DEMO_PATTERNS = [
    r"demo",
    r"example lesson",
    r"sample lesson",
    r"what can you do",
    r"show me what you",
]

GAP_ANALYSIS_PATTERNS = [
    r"curriculum gaps?",
    r"gap analysis",
    r"what am i missing",
    r"what haven't i covered",
    r"what haven.t i covered",
]

SWITCH_MODEL_PATTERNS = [
    r"switch to ollama",
    r"use anthropic",
    r"change model",
    r"switch to openai",
]

SCHEDULE_PATTERNS = [
    r"remind me",
    r"send me a digest",
    r"morning reminder",
    r"stop reminder",
    r"what's scheduled",
    r"what.s scheduled",
    r"my schedule",
]

EXPORT_SLIDES_PATTERNS = [
    r"export slides",
    r"make slides",
    r"powerpoint",
    r"pptx",
    r"slide deck",
]

EXPORT_HANDOUT_PATTERNS = [
    r"export\s+(?:the\s+)?handout",
    r"download\s+(?:the\s+)?handout",
    r"print\s+(?:the\s+)?handout",
    r"export\s+(?:the\s+)?worksheet",
    r"save\s+(?:the\s+)?handout",
]

EXPORT_DOC_PATTERNS = [
    r"export doc",
    r"word doc",
    r"docx",
]

SHOW_PERSONA_PATTERNS = [
    r"my persona",
    r"my teaching style",
    r"show persona",
]

SHOW_SETTINGS_PATTERNS = [
    r"my settings",
    r"show settings",
    r"show config",
]

SHOW_PROGRESS_PATTERNS = [
    r"my progress",
    r"show progress",
]

SHOW_FEEDBACK_PATTERNS = [
    r"my feedback",
    r"feedback summary",
    r"my ratings",
]


def _any_match(text: str, patterns: list[str]) -> bool:
    """Return True if text matches any pattern (case-insensitive)."""
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _extract_topic(text: str) -> str | None:
    """Try to extract the lesson/unit topic from a message."""
    # "lesson on photosynthesis" / "unit on the Civil War" / "plan a lesson about fractions"
    patterns = [
        r"(?:on|about|for|covering|teaching)\s+(.+?)(?:\s+for|\s+grade|\s+in|\s+week|\.$|$)",
        r"(?:lesson|unit|plan|worksheet|quiz)\s+(?:on|about|for)\s+(.+?)(?:\s+for|\s+grade|$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            topic = m.group(1).strip().rstrip(".,!?")
            if len(topic) > 2:
                return topic
    return None


def _extract_grade(text: str) -> str | None:
    """Try to extract grade level."""
    m = re.search(r"(?:grade|gr\.?)\s*(\d+|k(?:indergarten)?)|(\d+)(?:st|nd|rd|th)\s+grade", text, re.IGNORECASE)
    if m:
        return (m.group(1) or m.group(2) or "").strip()
    # Also catch "8th grade", "grade 8", "8th graders"
    m = re.search(r"(\d+)(?:st|nd|rd|th)?\s*grad(?:e|ers?)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _extract_weeks(text: str) -> int | None:
    """Try to extract duration in weeks."""
    m = re.search(r"(\d+)\s*(?:week|wk)s?", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if re.search(r"one\s+week", text, re.IGNORECASE):
        return 1
    if re.search(r"two\s+weeks?", text, re.IGNORECASE):
        return 2
    if re.search(r"three\s+weeks?", text, re.IGNORECASE):
        return 3
    return None


def _extract_url(text: str) -> str | None:
    """Extract a URL from the message."""
    m = re.search(r"https?://\S+", text)
    return m.group(0).rstrip(".,)>]") if m else None


def parse_intent(message: str) -> ParsedIntent:
    """Parse a teacher message and return the detected intent with extracted params."""
    text = message.strip()

    # Setup & Config (check early — these are high priority)
    if _any_match(text, DRIVE_PATTERNS):
        return ParsedIntent(
            intent=Intent.CONNECT_DRIVE,
            url=_extract_url(text),
            raw=text,
        )

    if _any_match(text, LOCAL_PATTERNS):
        # Try to extract path
        m = re.search(r"(/[\w/.-]+|~/[\w/.-]+)", text)
        return ParsedIntent(
            intent=Intent.CONNECT_LOCAL,
            url=m.group(0) if m else None,
            raw=text,
        )

    if _any_match(text, SETUP_PATTERNS):
        return ParsedIntent(intent=Intent.SETUP, raw=text)

    if _any_match(text, STATUS_PATTERNS):
        return ParsedIntent(intent=Intent.SHOW_STATUS, raw=text)

    if _any_match(text, HELP_PATTERNS):
        return ParsedIntent(intent=Intent.HELP, raw=text)

    # New intents from tg.py _detect_intent (check before generic patterns)
    if _any_match(text, DEMO_PATTERNS):
        return ParsedIntent(intent=Intent.DEMO, raw=text)

    if _any_match(text, GAP_ANALYSIS_PATTERNS):
        return ParsedIntent(intent=Intent.GAP_ANALYSIS, raw=text)

    if _any_match(text, SWITCH_MODEL_PATTERNS):
        return ParsedIntent(intent=Intent.SWITCH_MODEL, raw=text)

    if _any_match(text, SCHEDULE_PATTERNS):
        return ParsedIntent(intent=Intent.SCHEDULE, raw=text)

    if _any_match(text, SHOW_PERSONA_PATTERNS):
        return ParsedIntent(intent=Intent.SHOW_PERSONA, raw=text)

    if _any_match(text, SHOW_SETTINGS_PATTERNS):
        return ParsedIntent(intent=Intent.SHOW_SETTINGS, raw=text)

    if _any_match(text, SHOW_PROGRESS_PATTERNS):
        return ParsedIntent(intent=Intent.SHOW_PROGRESS, raw=text)

    if _any_match(text, SHOW_FEEDBACK_PATTERNS):
        return ParsedIntent(intent=Intent.SHOW_FEEDBACK, raw=text)

    if _any_match(text, EXPORT_SLIDES_PATTERNS):
        return ParsedIntent(intent=Intent.EXPORT_SLIDES, format="slides", raw=text)

    if _any_match(text, EXPORT_HANDOUT_PATTERNS):
        return ParsedIntent(intent=Intent.EXPORT_HANDOUT, format="handout", raw=text)

    if _any_match(text, EXPORT_DOC_PATTERNS):
        return ParsedIntent(intent=Intent.EXPORT_DOC, format="doc", raw=text)

    # Student bot management (check before general patterns)
    if _any_match(text, STUDENT_BOT_PATTERNS):
        return ParsedIntent(intent=Intent.START_STUDENT_BOT, raw=text)

    if _any_match(text, STUDENT_REPORT_PATTERNS):
        return ParsedIntent(intent=Intent.SHOW_STUDENT_REPORT, raw=text)

    if _any_match(text, HINT_MODE_PATTERNS):
        return ParsedIntent(intent=Intent.SET_HINT_MODE, raw=text)

    # Standards search (check before general search)
    if _any_match(text, STANDARDS_PATTERNS):
        return ParsedIntent(
            intent=Intent.SEARCH_STANDARDS,
            grade=_extract_grade(text),
            query=text,
            raw=text,
        )

    # Web search
    if _any_match(text, SEARCH_PATTERNS):
        return ParsedIntent(
            intent=Intent.WEB_SEARCH,
            query=text,
            raw=text,
        )

    # Export & Share
    for fmt, patterns in EXPORT_PATTERNS.items():
        if _any_match(text, patterns):
            intent_map = {
                "pdf": Intent.EXPORT_PDF,
                "classroom": Intent.EXPORT_CLASSROOM,
                "share": Intent.SHARE_STUDENTS,
            }
            return ParsedIntent(intent=intent_map[fmt], format=fmt, raw=text)

    # Year-level planning (check before unit — "year plan" could match unit patterns)
    if _any_match(text, YEAR_MAP_PATTERNS):
        return ParsedIntent(
            intent=Intent.GENERATE_YEAR_MAP,
            subject=_extract_topic(text),
            grade=_extract_grade(text),
            raw=text,
        )

    if _any_match(text, PACING_PATTERNS):
        return ParsedIntent(
            intent=Intent.GENERATE_PACING_GUIDE,
            raw=text,
        )

    # Generation (most common use case)
    if _any_match(text, UNIT_PATTERNS):
        return ParsedIntent(
            intent=Intent.GENERATE_UNIT,
            topic=_extract_topic(text),
            grade=_extract_grade(text),
            weeks=_extract_weeks(text),
            raw=text,
        )

    if _any_match(text, ASSESSMENT_PATTERNS):
        return ParsedIntent(
            intent=Intent.GENERATE_ASSESSMENT,
            topic=_extract_topic(text),
            grade=_extract_grade(text),
            raw=text,
        )

    if _any_match(text, MATERIALS_PATTERNS):
        return ParsedIntent(
            intent=Intent.GENERATE_MATERIALS,
            topic=_extract_topic(text),
            grade=_extract_grade(text),
            raw=text,
        )

    if _any_match(text, BELLRINGER_PATTERNS):
        return ParsedIntent(
            intent=Intent.GENERATE_BELLRINGER,
            topic=_extract_topic(text),
            raw=text,
        )

    if _any_match(text, LESSON_PATTERNS):
        return ParsedIntent(
            intent=Intent.GENERATE_LESSON,
            topic=_extract_topic(text),
            grade=_extract_grade(text),
            raw=text,
        )

    # Differentiation
    if re.search(r"(differentiat|iep|accommodat|modif|struggling|advanced|ell|english learner)", text, re.IGNORECASE):
        return ParsedIntent(
            intent=Intent.GENERATE_DIFFERENTIATION,
            topic=_extract_topic(text),
            raw=text,
        )

    return ParsedIntent(intent=Intent.UNKNOWN, raw=text)


def needs_clarification(parsed: ParsedIntent) -> str | None:
    """
    Return a clarifying question if we're missing critical info,
    or None if we have enough to proceed.
    """
    if parsed.intent == Intent.GENERATE_UNIT:
        if not parsed.topic:
            return "What topic should the unit cover?"
        if not parsed.weeks:
            return f"How many weeks for the {parsed.topic} unit? (1-4 weeks is typical)"

    if parsed.intent == Intent.GENERATE_YEAR_MAP and not parsed.subject and not parsed.grade:
        return "What subject and grade level? (e.g., '8th grade Math')"

    if parsed.intent in (Intent.GENERATE_LESSON, Intent.GENERATE_MATERIALS, Intent.GENERATE_ASSESSMENT):
        if not parsed.topic:
            return "What topic should I create this for?"

    if parsed.intent == Intent.CONNECT_DRIVE and not parsed.url:
        return "Could you share the Google Drive folder link? (Right-click the folder → Share → Copy link)"

    if parsed.intent == Intent.CONNECT_LOCAL and not parsed.url:
        return "What's the path to your lesson plan folder? (e.g., /Users/yourname/Teaching/)"

    return None
