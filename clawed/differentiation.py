"""IEP and differentiation intelligence layer.

Generates modified lesson plans for IEP students, 504 accommodation notes,
and tiered assignments for differentiated instruction.  Every teacher with
IEP students spends hours creating modified versions — this module automates
the heavy lifting while keeping the teacher in control.
"""

from __future__ import annotations

import json
from pathlib import Path

from clawed.llm import LLMClient
from clawed.model_router import route as route_model
from clawed.models import (
    AppConfig,
    DailyLesson,
    DifferentiationNotes,
    IEPProfile,
    WorksheetItem,
)

PROMPT_DIR = Path(__file__).parent / "prompts"


# ── IEP lesson modifications ─────────────────────────────────────────────


async def generate_iep_lesson_modifications(
    lesson: DailyLesson,
    iep_profiles: list[IEPProfile],
    config: AppConfig | None = None,
) -> dict[str, DailyLesson]:
    """Generate a modified lesson for each IEP student.

    Returns a mapping of student_name → modified DailyLesson.
    Each version applies that student's specific accommodations, modifications,
    and aligns activities to their IEP goals.
    """
    if not iep_profiles:
        return {}

    prompt_template = (PROMPT_DIR / "iep_modification.txt").read_text(encoding="utf-8")

    exit_ticket_text = "; ".join(q.question for q in lesson.exit_ticket) or "None"

    cfg = config or AppConfig.load()
    cfg = route_model("iep_modification", cfg)
    client = LLMClient(cfg)

    results: dict[str, DailyLesson] = {}

    for profile in iep_profiles:
        prompt = (
            prompt_template
            .replace("{lesson_title}", lesson.title)
            .replace("{objective}", lesson.objective)
            .replace("{standards}", ", ".join(lesson.standards) or "None specified")
            .replace("{do_now}", lesson.do_now)
            .replace("{direct_instruction}", lesson.direct_instruction[:1500])
            .replace("{guided_practice}", lesson.guided_practice[:1500])
            .replace("{independent_work}", lesson.independent_work[:1000])
            .replace("{exit_ticket}", exit_ticket_text)
            .replace("{homework}", lesson.homework or "None")
            .replace("{student_name}", profile.student_name)
            .replace("{disability_type}", profile.disability_type or "Not specified")
            .replace("{accommodations}", "\n".join(f"- {a}" for a in profile.accommodations) or "None listed")
            .replace("{modifications}", "\n".join(f"- {m}" for m in profile.modifications) or "None listed")
            .replace("{goals}", "\n".join(f"- {g}" for g in profile.goals) or "None listed")
        )

        data = await client.generate_json(
            prompt=prompt,
            system="You are an IEP specialist. Respond only with valid JSON.",
            temperature=0.4,
            max_tokens=8192,
        )

        # Backfill the required identity fields the model tends to drop or null
        # out. A differentiated version of lesson N is still lesson N with the
        # same objective, so anchor those from the source lesson rather than
        # letting a missing key 500 the request (DailyLesson.lesson_number is a
        # required int; `objective` is required too).
        if isinstance(data, dict):
            if data.get("lesson_number") is None:
                data["lesson_number"] = lesson.lesson_number
            if not data.get("objective"):
                data["objective"] = lesson.objective
            if not data.get("title"):
                data["title"] = lesson.title

        results[profile.student_name] = DailyLesson.model_validate(data)

    return results


# ── 504 accommodations ────────────────────────────────────────────────────


async def generate_504_accommodations(
    lesson: DailyLesson,
    accommodations: list[str],
    config: AppConfig | None = None,
) -> DifferentiationNotes:
    """Generate specific 504 accommodation notes for a lesson.

    Unlike IEP modifications, 504 accommodations don't change WHAT the student
    learns — they change HOW the student accesses the same curriculum.
    """
    if not accommodations:
        return DifferentiationNotes()

    prompt_template = (PROMPT_DIR / "504_accommodations.txt").read_text(encoding="utf-8")

    prompt = (
        prompt_template
        .replace("{lesson_title}", lesson.title)
        .replace("{objective}", lesson.objective)
        .replace("{grade_level}", "Not specified")
        .replace("{do_now}", lesson.do_now)
        .replace("{direct_instruction}", lesson.direct_instruction[:1500])
        .replace("{guided_practice}", lesson.guided_practice[:1500])
        .replace("{independent_work}", lesson.independent_work[:1000])
        .replace("{accommodations_list}", "\n".join(f"- {a}" for a in accommodations))
    )

    cfg = config or AppConfig.load()
    cfg = route_model("differentiation", cfg)
    client = LLMClient(cfg)

    data = await client.generate_json(
        prompt=prompt,
        system="You are a 504 accommodation specialist. Respond only with valid JSON.",
        temperature=0.4,
    )

    return DifferentiationNotes.model_validate(data)


# ── Tiered assignments ────────────────────────────────────────────────────


async def generate_tiered_assignments(
    topic: str,
    grade: str,
    tiers: int = 3,
    config: AppConfig | None = None,
) -> list[WorksheetItem]:
    """Generate tiered worksheet items — same concept at multiple difficulty levels.

    Tier encoding in item_number:
      - Tier 1 (Approaching): items 1-99
      - Tier 2 (On-Level): items 100-199
      - Tier 3 (Advanced): items 200-299
      - Additional tiers continue the pattern.
    """
    prompt_template = (PROMPT_DIR / "tiered_assignments.txt").read_text(encoding="utf-8")

    prompt = (
        prompt_template
        .replace("{topic}", topic)
        .replace("{grade_level}", grade)
        .replace("{num_tiers}", str(tiers))
    )

    cfg = config or AppConfig.load()
    cfg = route_model("differentiation", cfg)
    client = LLMClient(cfg)

    data = await client.generate_json(
        prompt=prompt,
        system="You are a differentiated instruction expert. Respond only with a valid JSON array.",
        temperature=0.5,
    )

    return [WorksheetItem.model_validate(item) for item in data]


# ── Helpers ───────────────────────────────────────────────────────────────


def load_iep_profiles(path: Path) -> list[IEPProfile]:
    """Load IEP profiles from a JSON file (array of profile objects)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = [raw]
    return [IEPProfile.model_validate(p) for p in raw]


def save_modified_lessons(
    modifications: dict[str, DailyLesson],
    output_dir: Path,
) -> list[Path]:
    """Save each student's modified lesson to a separate JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    from clawed import _safe_filename

    for student_name, lesson in modifications.items():
        safe_name = _safe_filename(student_name)
        path = output_dir / f"iep_modified_{safe_name}.json"
        path.write_text(lesson.model_dump_json(indent=2), encoding="utf-8")
        paths.append(path)
    return paths


def save_tiered_assignments(
    items: list[WorksheetItem],
    output_dir: Path,
    topic: str,
) -> Path:
    """Save tiered assignment items to a JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    from clawed import _safe_filename

    safe_topic = _safe_filename(topic)
    path = output_dir / f"tiered_{safe_topic}.json"
    data = [item.model_dump() for item in items]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
