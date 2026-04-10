"""Pedagogical Fingerprint Evolution — conservative persona drift tracking.

Tracks changes to a teacher's persona over time.  Changes require 2+
consistent signals (e.g. two separate ingestion runs that both detect
the same style shift) before they are applied.  This prevents a single
noisy extraction from overwriting the teacher's carefully-built identity.

Flow:
    1. New files ingested → ``record_ingestion_changes()`` compares old/new
    2. Candidates accumulate in ``~/.eduagent/persona_candidates.json``
    3. Each feedback cycle calls ``get_confirmed_changes()``
    4. Only candidates with confirmations >= 2 are applied
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from clawed.models import TeacherPersona

logger = logging.getLogger(__name__)

# ── Evolvable fields ────────────────────────────────────────────────

_EVOLVABLE_FIELDS: list[str] = [
    "teaching_style",
    "do_now_style",
    "exit_ticket_style",
    "source_types",
    "activity_patterns",
    "scaffolding_moves",
    "signature_moves",
    "handout_style",
]

# ── Confirmation threshold ──────────────────────────────────────────

_CONFIRMATION_THRESHOLD = 2

# ── Candidate file path ────────────────────────────────────────────


def _candidates_path() -> Path:
    base = Path(os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent")))
    return base / "persona_candidates.json"


def _load_candidates() -> list[dict[str, Any]]:
    path = _candidates_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.debug("Could not read persona candidates file; starting fresh")
        return []


def _save_candidates(candidates: list[dict[str, Any]]) -> None:
    path = _candidates_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidates, indent=2, default=str), encoding="utf-8")


# ── Serialization helper ───────────────────────────────────────────


def _serialize(value: Any) -> Any:
    """Convert a persona field value into a JSON-safe representation."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


# ── Core comparison logic ──────────────────────────────────────────


def _compare_personas(
    old: TeacherPersona,
    new: TeacherPersona,
) -> list[dict[str, Any]]:
    """Compare two personas field-by-field across evolvable fields.

    Returns a list of ``{"field": ..., "old_value": ..., "new_value": ...}``
    dicts — one per changed field.
    """
    changes: list[dict[str, Any]] = []
    for field in _EVOLVABLE_FIELDS:
        old_val = _serialize(getattr(old, field, None))
        new_val = _serialize(getattr(new, field, None))
        if old_val != new_val:
            changes.append(
                {
                    "field": field,
                    "old_value": old_val,
                    "new_value": new_val,
                }
            )
    return changes


def _build_candidate_changes(
    old: TeacherPersona,
    new: TeacherPersona,
    source: str = "ingestion",
) -> list[dict[str, Any]]:
    """Wrap comparison results into timestamped candidate entries."""
    raw_changes = _compare_personas(old, new)
    now_iso = datetime.now(timezone.utc).isoformat()
    candidates: list[dict[str, Any]] = []
    for change in raw_changes:
        candidates.append(
            {
                "field": change["field"],
                "old_value": change["old_value"],
                "new_value": change["new_value"],
                "source": source,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "confirmations": 1,
            }
        )
    return candidates


# ── Rating pattern analysis ────────────────────────────────────────


def _analyze_rating_patterns(
    ratings: list[tuple[int, str]],
) -> list[dict[str, Any]]:
    """Analyze ``(rating, notes)`` tuples for style-shift signals.

    Requires a minimum of 10 ratings to produce any output — small
    sample sizes are too noisy to act on.
    """
    if len(ratings) < 10:
        return []

    signals: list[dict[str, Any]] = []

    # Split into halves to detect trend shifts
    mid = len(ratings) // 2
    first_half = ratings[:mid]
    second_half = ratings[mid:]

    first_avg = sum(r for r, _ in first_half) / len(first_half) if first_half else 0
    second_avg = sum(r for r, _ in second_half) / len(second_half) if second_half else 0

    if abs(second_avg - first_avg) >= 0.5:
        direction = "improving" if second_avg > first_avg else "declining"
        signals.append(
            {
                "type": "rating_trend",
                "direction": direction,
                "first_half_avg": round(first_avg, 2),
                "second_half_avg": round(second_avg, 2),
            }
        )

    # Look for keyword patterns in notes
    all_notes = " ".join(n.lower() for _, n in ratings if n)
    style_keywords = {
        "inquiry": "inquiry_based",
        "socratic": "socratic",
        "direct": "direct_instruction",
        "project": "project_based",
        "workshop": "workshop",
    }
    for keyword, style in style_keywords.items():
        if all_notes.count(keyword) >= 3:
            signals.append(
                {
                    "type": "style_keyword",
                    "keyword": keyword,
                    "suggested_style": style,
                    "occurrences": all_notes.count(keyword),
                }
            )

    return signals


# ── Public API ─────────────────────────────────────────────────────


def record_ingestion_changes(
    old_persona: TeacherPersona,
    new_persona: TeacherPersona,
) -> list[dict[str, Any]]:
    """Record persona changes detected during file ingestion.

    Compares old and new personas.  If a candidate for the same
    field+new_value already exists, increments its confirmation count
    instead of adding a duplicate.  Persists to disk.
    """
    new_candidates = _build_candidate_changes(old_persona, new_persona, source="ingestion")
    if not new_candidates:
        return []

    existing = _load_candidates()
    now_iso = datetime.now(timezone.utc).isoformat()

    for nc in new_candidates:
        # Look for an existing candidate with the same field and new_value
        matched = False
        for ec in existing:
            if ec["field"] == nc["field"] and ec["new_value"] == nc["new_value"]:
                ec["confirmations"] += 1
                ec["last_seen"] = now_iso
                matched = True
                break
        if not matched:
            existing.append(nc)

    _save_candidates(existing)
    logger.info(
        "Recorded %d persona change candidate(s) from ingestion",
        len(new_candidates),
    )
    return new_candidates


def get_confirmed_changes() -> list[dict[str, Any]]:
    """Return candidates that have reached the confirmation threshold."""
    candidates = _load_candidates()
    return [c for c in candidates if c.get("confirmations", 0) >= _CONFIRMATION_THRESHOLD]


def apply_confirmed_changes(
    persona: TeacherPersona,
) -> tuple[TeacherPersona, list[str]]:
    """Apply confirmed changes to a persona and clear them from candidates.

    Returns ``(updated_persona, list_of_change_descriptions)``.
    """
    confirmed = get_confirmed_changes()
    if not confirmed:
        return persona, []

    # Work on a mutable dict representation
    data = persona.model_dump()
    descriptions: list[str] = []
    applied_fields: set[str] = set()

    for change in confirmed:
        field = change["field"]
        new_value = change["new_value"]
        old_value = change.get("old_value", "unknown")

        if field not in _EVOLVABLE_FIELDS:
            continue

        data[field] = new_value
        applied_fields.add(field)

        # Human-readable description
        old_display = old_value if not isinstance(old_value, list) else ", ".join(str(v) for v in old_value)
        new_display = new_value if not isinstance(new_value, list) else ", ".join(str(v) for v in new_value)
        descriptions.append(f"{field}: {old_display} -> {new_display}")

    if not descriptions:
        return persona, []

    updated = TeacherPersona.model_validate(data)

    # Remove applied candidates from the file
    candidates = _load_candidates()
    remaining = [
        c
        for c in candidates
        if not (c["field"] in applied_fields and c.get("confirmations", 0) >= _CONFIRMATION_THRESHOLD)
    ]
    _save_candidates(remaining)

    logger.info("Applied %d persona evolution(s): %s", len(descriptions), "; ".join(descriptions))
    return updated, descriptions
