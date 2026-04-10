"""Voice-match validation — lightweight rule-based checks after lesson generation.

Runs after generation but before export.  Catches the most obvious mismatches
(wrong address term, wrong Do Now style) and surfaces them as advisory notes so
the teacher can request adjustments.  Never blocks export.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.models import TeacherPersona

# ── Address terms we recognise ────────────────────────────────────────────
_ADDRESS_TERMS: tuple[str, ...] = (
    "friends",
    "scholars",
    "historians",
    "scientists",
    "mathematicians",
    "students",
    "class",
    "team",
    "everybody",
    "everyone",
)

# Pre-compiled case-insensitive word-boundary patterns for each term.
_ADDRESS_TERM_RES: dict[str, re.Pattern[str]] = {
    term: re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in _ADDRESS_TERMS
}

# ── Do Now style classifiers ─────────────────────────────────────────────
_SCENARIO_RE = re.compile(
    r"\b(?:imagine|pretend|what\s+if|what\s+would\s+you"
    r"|you\s+are|you\s+just|you\s+wake|you\s+discover)\b",
    re.IGNORECASE,
)

_RECALL_RE = re.compile(
    r"\b(?:what\s+do\s+you\s+remember|what\s+do\s+you\s+know"
    r"|what\s+do\s+you\s+recall|list\s+three|define\b)"
    r"|yesterday.*\bwhat\b|last\s+class.*\bwhat\b",
    re.IGNORECASE,
)

_OPINION_RE = re.compile(
    r"\b(?:do\s+you\s+think|do\s+you\s+believe|do\s+you\s+agree"
    r"|should\b.*\?|is\s+it\s+fair|is\s+it\s+right|is\s+it\s+just)\b",
    re.IGNORECASE,
)


# ── Data structures ──────────────────────────────────────────────────────
@dataclass
class VoiceCheckResult:
    """Result of a post-generation voice-match check."""

    address_term_ok: bool = True
    do_now_style_ok: bool = True
    structure_ok: bool = True
    passed: bool = True
    issues: list[str] = field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────
def _detect_do_now_type(text: str) -> str:
    """Classify a Do Now prompt as 'scenario', 'recall', 'opinion', or 'other'.

    Uses simple regex heuristics.  When multiple signals are present the
    first match in priority order (scenario > recall > opinion) wins, which
    matches how most teachers describe their Do Now style.
    """
    if not text:
        return "other"
    if _SCENARIO_RE.search(text):
        return "scenario"
    if _RECALL_RE.search(text):
        return "recall"
    if _OPINION_RE.search(text):
        return "opinion"
    return "other"


def _extract_address_terms(text: str) -> set[str]:
    """Return the set of known student address terms found in *text*."""
    if not text:
        return set()
    found: set[str] = set()
    for term, pattern in _ADDRESS_TERM_RES.items():
        if pattern.search(text):
            found.add(term)
    return found


# ── Main checker ─────────────────────────────────────────────────────────
def check_voice_match(
    persona: TeacherPersona,
    do_now: str = "",
    direct_instruction_opening: str = "",
) -> VoiceCheckResult:
    """Run lightweight voice-match checks against a generated lesson.

    If the persona carries no voice data (no *voice_sample*, no
    *do_now_style*, no *signature_moves*) the check passes immediately —
    there is nothing to compare against.

    Returns a :class:`VoiceCheckResult` with advisory issues.
    """
    result = VoiceCheckResult()

    has_voice_sample = bool(getattr(persona, "voice_sample", ""))
    has_do_now_style = bool(getattr(persona, "do_now_style", ""))
    has_signature_moves = bool(getattr(persona, "signature_moves", None))

    # Nothing to check — pass gracefully.
    if not (has_voice_sample or has_do_now_style or has_signature_moves):
        return result

    # Combine generated text for address-term scanning.
    generated_text = f"{do_now} {direct_instruction_opening}"

    # ── Check 1: Address terms ────────────────────────────────────────
    # Build the teacher's expected address terms from voice_sample +
    # signature_moves.
    persona_text_parts: list[str] = []
    if has_voice_sample:
        persona_text_parts.append(persona.voice_sample)
    if has_signature_moves:
        persona_text_parts.extend(persona.signature_moves)
    persona_text = " ".join(persona_text_parts)

    expected_terms = _extract_address_terms(persona_text)
    if expected_terms:
        found_terms = _extract_address_terms(generated_text)
        if not expected_terms & found_terms:
            # The generated text uses none of the teacher's address terms.
            result.address_term_ok = False
            expected_str = ", ".join(sorted(expected_terms))
            if found_terms:
                found_str = ", ".join(sorted(found_terms))
                result.issues.append(f"Expected address term '{expected_str}' but found '{found_str}' instead")
            else:
                result.issues.append(f"Expected address term '{expected_str}' but none found in generated text")

    # ── Check 2: Do Now style ─────────────────────────────────────────
    if has_do_now_style and do_now:
        style_lower = persona.do_now_style.lower()
        detected_type = _detect_do_now_type(do_now)

        # If the teacher says "scenario" or "analogy" but the Do Now is
        # classified as "recall", that is a mismatch.
        expects_scenario = any(kw in style_lower for kw in ("scenario", "analogy"))
        if expects_scenario and detected_type == "recall":
            result.do_now_style_ok = False
            result.issues.append(
                "Do Now style mismatch: teacher prefers "
                "scenario/analogy-based Do Nows but generated a "
                "recall-type question"
            )

        # Symmetric check: teacher expects recall but we generated scenario.
        expects_recall = bool(re.search(r"\b(?:recall|review|prior\s+knowledge)\b", style_lower))
        if expects_recall and detected_type == "scenario":
            result.do_now_style_ok = False
            result.issues.append(
                "Do Now style mismatch: teacher prefers "
                "recall/review-based Do Nows but generated a "
                "scenario-type question"
            )

    # ── Final verdict ─────────────────────────────────────────────────
    result.passed = result.address_term_ok and result.do_now_style_ok and result.structure_ok
    return result
