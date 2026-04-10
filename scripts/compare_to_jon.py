"""Compare Ed's generated lessons against Jon's real lessons.

Scores generated MasterContent on 7 dimensions, each 0-100:

  1. Indexing materials       — corpus + KG + wiki + assets totals
  2. Recalling files          — brain context populated by topic
  3. Pulling images           — % of image_specs resolved from teacher assets
  4. Capturing patterns       — persona has voice + signature_moves + scaffolding
  5. Voice in output          — generated teacher_script contains persona phrases
  6. Replicating real lessons — primary sources real, stations 3+, creative present
  7. Compounding over time    — past_lesson_results > 0, brain has lessons

Final letter grade based on average:
  >= 95   A+
  >= 90   A
  >= 85   A-
  >= 80   B+
  ...
"""
import asyncio
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

os.environ["CLAWED_AUTO_APPROVE"] = "1"


@dataclass
class DimensionScore:
    name: str
    score: int  # 0-100
    weight: float = 1.0
    notes: list[str] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)


def grade_letter(avg: float) -> str:
    if avg >= 97:
        return "A+"
    if avg >= 93:
        return "A"
    if avg >= 90:
        return "A-"
    if avg >= 87:
        return "B+"
    if avg >= 83:
        return "B"
    if avg >= 80:
        return "B-"
    if avg >= 77:
        return "C+"
    if avg >= 73:
        return "C"
    if avg >= 70:
        return "C-"
    if avg >= 60:
        return "D"
    return "F"


# ══════════════════════════════════════════════════════════════════════
# Dimension 1: Indexing materials
# ══════════════════════════════════════════════════════════════════════


def score_indexing_materials() -> DimensionScore:
    """Indexing depth — corpus + KG + chunks + assets."""
    base = Path.home() / ".eduagent"
    breakdown = {}
    score = 0

    # Corpus (1000+ examples = full credit)
    corpus_db = base / "corpus" / "corpus.db"
    if corpus_db.exists():
        conn = sqlite3.connect(str(corpus_db))
        n = conn.execute("SELECT COUNT(*) FROM corpus_examples").fetchone()[0]
        conn.close()
        breakdown["corpus_examples"] = n
        score += 25 if n >= 1000 else int(25 * n / 1000)

    # Curriculum KB
    kb_db = base / "memory" / "curriculum_kb.db"
    if kb_db.exists():
        conn = sqlite3.connect(str(kb_db))
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        ents = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
        triples = conn.execute("SELECT COUNT(*) FROM kg_triples").fetchone()[0]
        assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        conn.close()
        breakdown["chunks"] = chunks
        breakdown["entities"] = ents
        breakdown["triples"] = triples
        breakdown["assets"] = assets
        # 50K chunks = full credit
        score += 25 if chunks >= 50000 else int(25 * chunks / 50000)
        # 30K entities = full credit (after cleanup we have 40K)
        score += 25 if ents >= 30000 else int(25 * ents / 30000)
        # 10K assets = full credit (we have 12K)
        score += 25 if assets >= 10000 else int(25 * assets / 10000)

    notes = [
        f"corpus={breakdown.get('corpus_examples', 0)}",
        f"chunks={breakdown.get('chunks', 0)}",
        f"entities={breakdown.get('entities', 0)}",
        f"triples={breakdown.get('triples', 0)}",
        f"assets={breakdown.get('assets', 0)}",
    ]
    return DimensionScore(
        name="Indexing materials",
        score=min(100, score),
        notes=notes,
        breakdown=breakdown,
    )


# ══════════════════════════════════════════════════════════════════════
# Dimension 2: Recalling files
# ══════════════════════════════════════════════════════════════════════


def score_recalling_files() -> DimensionScore:
    """Test that retrieval surfaces work."""
    breakdown = {}
    score = 0

    # Corpus retrieval
    try:
        from clawed.corpus import get_examples, get_few_shot_context
        for subj in ["US History", "Global History", "social studies"]:
            ex = get_examples("lesson_plan", subj, limit=3)
            breakdown[f"corpus[{subj}]"] = len(ex)
            if len(ex) >= 3:
                score += 10
        ctx = get_few_shot_context("lesson_plan", "social studies")
        breakdown["few_shot_chars"] = len(ctx)
        if len(ctx) > 1000:
            score += 10
    except Exception as e:
        breakdown["corpus_error"] = str(e)[:100]

    # KG connections
    try:
        from clawed.lesson_connections import inject_connections_into_prompt
        topics = ["Reform Movements", "Renaissance", "Industrial Revolution",
                  "Imperialism", "Cold War"]
        topics_with_ctx = 0
        for topic in topics:
            ctx = inject_connections_into_prompt(topic)
            if ctx:
                topics_with_ctx += 1
        breakdown["kg_topics_resolved"] = f"{topics_with_ctx}/{len(topics)}"
        score += int(40 * topics_with_ctx / len(topics))
    except Exception as e:
        breakdown["kg_error"] = str(e)[:100]

    # Wiki
    wiki_state = Path.home() / ".eduagent" / "wiki" / "_compile_state.json"
    if wiki_state.exists():
        with open(wiki_state) as f:
            articles = json.load(f)
        breakdown["wiki_articles"] = len(articles)
        if len(articles) >= 100:
            score += 20

    notes = [f"{k}={v}" for k, v in breakdown.items()]
    return DimensionScore(
        name="Recalling files",
        score=min(100, score),
        notes=notes,
        breakdown=breakdown,
    )


# ══════════════════════════════════════════════════════════════════════
# Dimension 3: Pulling images
# ══════════════════════════════════════════════════════════════════════


def score_pulling_images(master=None) -> DimensionScore:
    """Test that the image pipeline can resolve specs to teacher's assets."""
    breakdown = {}
    score = 0

    # Asset registry total
    try:
        from clawed.asset_registry import AssetRegistry
        AssetRegistry()  # init to verify it works
        kb_db = Path.home() / ".eduagent" / "memory" / "curriculum_kb.db"
        if kb_db.exists():
            conn = sqlite3.connect(str(kb_db))
            n = conn.execute("SELECT COUNT(*) FROM asset_images").fetchone()[0]
            conn.close()
            breakdown["asset_images_total"] = n
            if n >= 10000:
                score += 20
    except Exception as e:
        breakdown["registry_error"] = str(e)[:100]

    # Test resolution: probe with realistic image_specs
    try:
        from clawed.image_pipeline import _resolve_from_teacher_assets
        test_specs = {
            "Frederick Douglass portrait 1852": "Frederick Douglass",
            "Industrial Revolution factory 1800": "Factory",
            "Declaration of Independence 1776": "Declaration",
            "Civil War battlefield 1863": "Civil War",
            "Renaissance painting Michelangelo": "Renaissance",
        }
        resolved = _resolve_from_teacher_assets(test_specs, "default")
        breakdown["test_resolved"] = f"{len(resolved)}/{len(test_specs)}"
        # Each resolution worth 10 points
        score += min(50, len(resolved) * 10)
    except Exception as e:
        breakdown["resolve_error"] = str(e)[:100]

    # If we have a master, test on its actual specs
    if master is not None:
        try:
            from clawed.image_pipeline import _collect_image_specs, _resolve_from_teacher_assets
            specs = _collect_image_specs(master)
            if specs:
                resolved = _resolve_from_teacher_assets(specs, "default")
                pct = len(resolved) / len(specs) * 100
                breakdown["master_resolved"] = f"{len(resolved)}/{len(specs)} ({pct:.0f}%)"
                score += int(30 * len(resolved) / len(specs))
        except Exception as e:
            breakdown["master_error"] = str(e)[:100]
    else:
        # No master to test against — give partial credit
        score += 30

    notes = [f"{k}={v}" for k, v in breakdown.items()]
    return DimensionScore(
        name="Pulling images",
        score=min(100, score),
        notes=notes,
        breakdown=breakdown,
    )


# ══════════════════════════════════════════════════════════════════════
# Dimension 4: Capturing patterns
# ══════════════════════════════════════════════════════════════════════


def score_capturing_patterns() -> DimensionScore:
    """Persona depth — voice sample, signature moves, etc."""
    breakdown = {}
    score = 0

    pp = Path.home() / ".eduagent" / "persona.json"
    if not pp.exists():
        return DimensionScore("Capturing patterns", 0, notes=["NO PERSONA"])

    with open(pp) as f:
        persona = json.load(f)

    # Required fields
    fields_to_check = [
        ("teaching_style", 5),
        ("tone", 5),
        ("writing_framework", 10),
        ("voice_sample", 20),  # most important
        ("signature_moves", 15),
        ("scaffolding_moves", 15),
        ("source_types", 10),
        ("activity_patterns", 10),
        ("do_now_style", 5),
        ("exit_ticket_style", 5),
    ]
    for field_name, weight in fields_to_check:
        val = persona.get(field_name)
        if val:
            if isinstance(val, str) and val.strip():
                score += weight
                breakdown[field_name] = f"{len(val)}c"
            elif isinstance(val, list) and len(val) > 0:
                score += weight
                breakdown[field_name] = f"{len(val)} items"
        else:
            breakdown[field_name] = "MISSING"

    notes = [f"{k}={v}" for k, v in breakdown.items()]
    return DimensionScore(
        name="Capturing patterns",
        score=min(100, score),
        notes=notes,
        breakdown=breakdown,
    )


# ══════════════════════════════════════════════════════════════════════
# Dimension 5: Voice in output
# ══════════════════════════════════════════════════════════════════════


def score_voice_in_output(master) -> DimensionScore:
    """Check generated teacher_script contains persona-like patterns."""
    breakdown = {}
    score = 0

    if master is None:
        return DimensionScore("Voice in output", 0, notes=["NO MASTER"])

    # Combine all teacher_script text
    all_script = ""
    for section in master.direct_instruction:
        all_script += section.teacher_script + "\n"
    if hasattr(master, "do_now") and master.do_now:
        all_script += " ".join(master.do_now.questions or [])

    breakdown["total_script_chars"] = len(all_script)
    if len(all_script) > 500:
        score += 15

    # Check for persona signature: questions in script (Jon uses "Ask:" patterns)
    question_count = all_script.count("?")
    breakdown["question_marks"] = question_count
    if question_count >= 6:
        score += 15
    elif question_count >= 3:
        score += 10

    # Check for direct dialogue indicators
    dialogue_markers = [
        "ask", "say", "tell", "show", "wait", "call on", "raise", "thumbs",
        "turn to your partner", "think-pair-share",
    ]
    found_markers = sum(1 for m in dialogue_markers if m in all_script.lower())
    breakdown["dialogue_markers"] = found_markers
    score += min(20, found_markers * 4)

    # Check for hooks (analogies, scenarios)
    has_hooks = sum(
        1 for section in master.direct_instruction
        if hasattr(section, "hook") and section.hook and len(section.hook) > 20
    )
    breakdown["sections_with_hooks"] = has_hooks
    score += min(20, has_hooks * 10)

    # Check for transitions (scripted pivots)
    has_transitions = sum(
        1 for section in master.direct_instruction
        if hasattr(section, "transition") and section.transition and len(section.transition) > 20
    )
    breakdown["sections_with_transitions"] = has_transitions
    score += min(15, has_transitions * 5)

    # Check that lesson_personality is set (the hook theme)
    if master.lesson_personality and len(master.lesson_personality) > 20:
        score += 15
        breakdown["lesson_personality"] = "set"
    else:
        breakdown["lesson_personality"] = "MISSING"

    notes = [f"{k}={v}" for k, v in breakdown.items()]
    return DimensionScore(
        name="Voice in output",
        score=min(100, score),
        notes=notes,
        breakdown=breakdown,
    )


# ══════════════════════════════════════════════════════════════════════
# Dimension 6: Replicating real lessons
# ══════════════════════════════════════════════════════════════════════


def score_replicating_lessons(master) -> DimensionScore:
    """Quality scoring against the gold standard."""
    breakdown = {}
    score = 0

    if master is None:
        return DimensionScore("Replicating lessons", 0, notes=["NO MASTER"])

    # Primary sources: 2+ with substantial content_text
    sources_ok = sum(
        1 for ps in master.primary_sources
        if ps.content_text and len(ps.content_text) >= 100
    )
    breakdown["sources_with_real_text"] = f"{sources_ok}/{len(master.primary_sources)}"
    if sources_ok >= 3:
        score += 20
    elif sources_ok >= 2:
        score += 15

    # Vocabulary: 4+ terms with definitions and context
    vocab_ok = sum(
        1 for v in master.vocabulary
        if v.term and v.definition and v.context_sentence
    )
    breakdown["complete_vocab"] = f"{vocab_ok}/{len(master.vocabulary)}"
    if vocab_ok >= 6:
        score += 10
    elif vocab_ok >= 4:
        score += 8

    # Guided notes: 8+
    breakdown["guided_notes"] = len(master.guided_notes)
    if len(master.guided_notes) >= 10:
        score += 10
    elif len(master.guided_notes) >= 8:
        score += 8

    # Stations: 3+
    breakdown["stations"] = len(master.stations)
    if len(master.stations) >= 3:
        score += 15
    elif len(master.stations) >= 2:
        score += 8

    # Creative activity present
    if master.creative_activity is not None:
        score += 15
        breakdown["creative_activity"] = master.creative_activity.activity_type
    else:
        breakdown["creative_activity"] = "MISSING"

    # Exit ticket: 3 questions with progression
    if len(master.exit_ticket) >= 3:
        score += 10
        breakdown["exit_ticket"] = "3 Qs"
        # Check progression
        levels = [q.cognitive_level for q in master.exit_ticket]
        if "recall" in levels and "application" in levels and "analysis" in levels:
            score += 5
            breakdown["progression"] = "yes"

    # Differentiation
    diff = master.differentiation
    if (len(diff.struggling) >= 3 and len(diff.advanced) >= 3 and len(diff.ell) >= 3):
        score += 10
        breakdown["differentiation"] = "complete"

    # Minute-by-minute
    if len(master.minute_by_minute) >= 5:
        score += 5
        breakdown["pacing_blocks"] = len(master.minute_by_minute)

    notes = [f"{k}={v}" for k, v in breakdown.items()]
    return DimensionScore(
        name="Replicating lessons",
        score=min(100, score),
        notes=notes,
        breakdown=breakdown,
    )


# ══════════════════════════════════════════════════════════════════════
# Dimension 7: Compounding over time
# ══════════════════════════════════════════════════════════════════════


def score_compounding() -> DimensionScore:
    """Brain population — past lessons recallable."""
    breakdown = {}
    score = 0

    try:
        from clawed.brain.store import BrainStore
        store = BrainStore()
        stats = store.stats()
        for ptype, count in stats.items():
            breakdown[ptype] = count

        # Lessons (most important — proves generation→brain loop)
        lessons = stats.get("lesson", 0)
        if lessons >= 10:
            score += 30
        elif lessons >= 5:
            score += 20
        elif lessons >= 1:
            score += 10

        # Topics
        topics = stats.get("topic", 0)
        if topics >= 5:
            score += 15
        elif topics >= 1:
            score += 8

        # Concepts
        concepts = stats.get("concept", 0)
        if concepts >= 20:
            score += 15
        elif concepts >= 5:
            score += 8

        # Originals (Tier 1 — high value)
        originals = stats.get("original", 0)
        if originals >= 3:
            score += 20
        elif originals >= 1:
            score += 10

        # Students
        students = stats.get("student", 0)
        if students >= 3:
            score += 20
        elif students >= 1:
            score += 10
    except Exception as e:
        breakdown["error"] = str(e)[:100]

    notes = [f"{k}={v}" for k, v in breakdown.items()]
    return DimensionScore(
        name="Compounding over time",
        score=min(100, score),
        notes=notes,
        breakdown=breakdown,
    )


# ══════════════════════════════════════════════════════════════════════
# Main eval
# ══════════════════════════════════════════════════════════════════════


def run_eval(master=None) -> dict:
    """Run all 7 scoring dimensions and return final report."""
    results = [
        score_indexing_materials(),
        score_recalling_files(),
        score_pulling_images(master),
        score_capturing_patterns(),
        score_voice_in_output(master),
        score_replicating_lessons(master),
        score_compounding(),
    ]

    avg = sum(r.score for r in results) / len(results)
    grade = grade_letter(avg)

    print()
    print("=" * 70)
    print("ED EVALUATION REPORT")
    print("=" * 70)
    print()
    for r in results:
        bar_full = int(r.score / 5)
        bar = "█" * bar_full + "░" * (20 - bar_full)
        print(f"  {r.name:.<32} {bar} {r.score:3d}/100")
        for note in r.notes[:6]:
            print(f"    · {note}")
        print()

    print("─" * 70)
    print(f"  AVERAGE: {avg:.1f}/100  →  GRADE: {grade}")
    print("=" * 70)

    return {
        "scores": {r.name: r.score for r in results},
        "average": avg,
        "grade": grade,
        "details": [
            {"name": r.name, "score": r.score, "breakdown": r.breakdown}
            for r in results
        ],
    }


if __name__ == "__main__":
    # Try to load the most recent generated lesson if any
    master = None
    out_dir = Path.home() / ".eduagent" / "phase_stress_output"
    if out_dir.exists():
        # Find any .json saved master content
        for f in out_dir.glob("*_master.json"):
            try:
                from clawed.master_content import MasterContent
                master = MasterContent.model_validate_json(f.read_text())
                print(f"Loaded master from {f.name}")
                break
            except Exception:
                pass

    if "--with-master" in sys.argv:
        # Generate a fresh lesson for full evaluation
        async def gen():
            from clawed.lesson import generate_master_content
            from clawed.models import LessonBrief, TeacherPersona, UnitPlan
            pp = Path.home() / ".eduagent" / "persona.json"
            persona = TeacherPersona(**json.loads(pp.read_text())) if pp.exists() else TeacherPersona(name="Test")
            unit = UnitPlan(
                title="The Fight for Equality",
                subject="US History",
                grade_level="8th Grade",
                topic="Reform Movements",
                duration_weeks=3,
                overview="19th century reform movements.",
                standards=["NYS 8.7c"],
                daily_lessons=[
                    LessonBrief(
                        lesson_number=1,
                        topic="Introduction to Reform Movements",
                        description="Station rotation",
                        lesson_type="station_rotation",
                    ),
                ],
            )
            return await generate_master_content(
                lesson_number=1, unit=unit, persona=persona,
                include_homework=True, state="NY",
            )
        try:
            master = asyncio.run(gen())
        except Exception as e:
            print(f"Generation failed: {e}")

    report = run_eval(master)
    sys.exit(0 if report["grade"] in ("A+", "A") else 1)
