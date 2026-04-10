"""Generate Week 1 lessons for all 3 courses.

Run on Windows with:
  C:\\Users\\jonan\\AppData\\Local\\Programs\\Python\\Python312\\python.exe -X utf8 gen_week1.py
"""
import asyncio
import json
import os
import sys

os.environ["CLAWED_AUTO_APPROVE"] = "1"

from clawed.models import (
    LessonBrief,
    TeacherPersona,
    UnitPlan,
)


def make_persona():
    """Build Jon's persona from the saved persona.json or defaults."""
    persona_path = os.path.expanduser("~/.eduagent/persona.json")
    if os.path.exists(persona_path):
        with open(persona_path) as f:
            data = json.load(f)
        try:
            return TeacherPersona(**data)
        except Exception:
            pass
    # Fallback
    return TeacherPersona(
        name="Mr. Maccarello's Teaching Style",
        teaching_style="direct_instruction",
        tone="warm, humorous, direct - uses real-world analogies and pop culture",
        structural_preferences=[
            "Do Now with real primary source",
            "I Do / We Do / You Do",
            "Station rotations and jigsaws",
            "Exit ticket with CRQ format",
            "REMEMBER T.E.A.",
        ],
        assessment_style="rubric_based",
        preferred_lesson_format="I Do / We Do / You Do with document analysis",
        favorite_strategies=[
            "Claim and Evidence framework",
            "Jigsaw with graphic organizer",
            "Philosophical Chairs debate",
            "Gallery Walk",
            "Primary source stations",
        ],
        subject_area="Social Studies",
        grade_levels=["8", "9", "10"],
    )


UNITS = [
    # 8th Grade US History — Unit 1: Reform Movements
    UnitPlan(
        title="The Fight for Equality: Reform Movements",
        subject="US History",
        grade_level="8th Grade",
        topic="Reform Movements and their Impacts",
        duration_weeks=3,
        overview=(
            "Students examine 19th-20th century reform movements including "
            "abolition, temperance, women's suffrage, and labor reform, "
            "evaluating how citizens organized to address social injustice."
        ),
        essential_questions=[
            "What does it mean to 'reform' a society, and who gets to decide what needs changing?",
            "How did movements like Women's Suffrage and Abolitionism use the 'Claim and Evidence' approach to change laws?",
        ],
        standards=["NYS K-8 SS Framework 8.7c", "C3 Framework D2.His.1.8-12"],
        daily_lessons=[
            LessonBrief(
                lesson_number=1,
                topic="Introduction to Reform Movements: Why People Fight for Change",
                description="Station rotation analyzing primary sources from four reform movements (abolition, temperance, labor, suffrage)",
                lesson_type="station_rotation",
            ),
            LessonBrief(
                lesson_number=2,
                topic="The Women's Suffrage Movement: The Fight for the 19th Amendment",
                description="Jigsaw activity analyzing Declaration of Sentiments, anti-suffrage pamphlets, 1913 march photo, 19th Amendment",
                lesson_type="jigsaw",
            ),
            LessonBrief(
                lesson_number=3,
                topic="Voices of Change: Reform Movement Research Project (Day 1)",
                description="Project launch - students select a reform movement and project format, begin research",
                lesson_type="project",
            ),
        ],
    ),
    # 9th Grade Global History — Unit 5: Renaissance
    UnitPlan(
        title="The Renaissance: Rebirth of Ideas",
        subject="Global History",
        grade_level="9th Grade",
        topic="Renaissance, Reformation, and Scientific Revolution",
        duration_weeks=4,
        overview=(
            "Students explore how the Renaissance transformed European society "
            "through Humanism, art, and scientific inquiry, and how these ideas "
            "spread from Italy across the continent."
        ),
        essential_questions=[
            "How does a change in how people think lead to a change in how they live?",
            "Why did the Renaissance start in Italy and how did it spread to the rest of Europe?",
        ],
        standards=["NYS Global 9.1", "NYS Global 9.2"],
        daily_lessons=[
            LessonBrief(
                lesson_number=1,
                topic="What Is Humanism? The Shift from God-Centered to Human-Centered Thinking",
                description="Document analysis comparing medieval vs Renaissance art and philosophy",
                lesson_type="document_analysis",
            ),
        ],
    ),
    # 10th Grade Global History — Unit 1: Industrialization
    UnitPlan(
        title="The Age of Modernization: Industrialization & Imperialism",
        subject="Global History",
        grade_level="10th Grade",
        topic="Industrialization and its Global Impact",
        duration_weeks=2,
        overview=(
            "Students examine how the Industrial Revolution changed everything - "
            "how people lived, worked, and organized society - and how this led "
            "directly to the scramble for colonies and global imperialism."
        ),
        essential_questions=[
            "How did the shift from handmade goods to machine manufacturing change the way people lived and worked?",
            "Why did powerful nations feel the need to conquer others to fuel their own economic growth?",
        ],
        standards=["NYS Global History Standard 9.1", "NYS Global History Standard 9.2"],
        daily_lessons=[
            LessonBrief(
                lesson_number=1,
                topic="From Farms to Factories: The Industrial Revolution Begins",
                description="Station rotation with primary sources from workers, factory owners, and reformers",
                lesson_type="station_rotation",
            ),
        ],
    ),
]


async def generate_one(unit, lesson_num, persona, output_dir):
    from clawed.lesson import generate_master_content
    from clawed.compile_teacher import compile_teacher_view
    from clawed.compile_student import compile_student_view

    label = f"{unit.grade_level} {unit.subject}"
    lesson_brief = unit.daily_lessons[lesson_num - 1]
    print(f"\n{'='*60}")
    print(f"GENERATING: {label}")
    print(f"  Topic: {lesson_brief.topic}")
    print(f"{'='*60}")

    try:
        master = await generate_master_content(
            lesson_number=lesson_num,
            unit=unit,
            persona=persona,
            include_homework=True,
            state="NY",
        )
        print(f"  -> MasterContent: {master.title}")
        print(f"     Primary sources: {len(master.primary_sources)}")
        print(f"     Guided notes: {len(master.guided_notes)}")
        print(f"     Exit ticket Qs: {len(master.exit_ticket)}")
        print(f"     Stations: {len(master.stations)}")

        # Check quality
        has_creative = hasattr(master, "creative_activity") and master.creative_activity
        has_jigsaw = hasattr(master, "jigsaw") and master.jigsaw
        print(f"     Creative activity: {bool(has_creative)}")
        print(f"     Jigsaw: {bool(has_jigsaw)}")
        print(f"     Personality: {master.lesson_personality[:80] if master.lesson_personality else 'MISSING'}")

        # Compile DOCX outputs
        os.makedirs(output_dir, exist_ok=True)
        images = {}  # no images for now

        teacher_path = await compile_teacher_view(master, images, output_dir)
        student_path = await compile_student_view(master, images, output_dir)
        print(f"  -> Teacher DOCX: {teacher_path}")
        print(f"  -> Student DOCX: {student_path}")

        return master
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    base_dir = os.path.expanduser("~/.eduagent/week1_gen")
    persona = make_persona()
    print(f"Persona: {persona.name}")
    print(f"Style: {persona.teaching_style}")
    print(f"Tone: {persona.tone[:60]}...")

    results = []
    for unit in UNITS:
        grade = unit.grade_level.split()[0].lower()
        subj = unit.subject.lower().replace(" ", "_")
        out_dir = os.path.join(base_dir, f"{grade}_{subj}")
        r = await generate_one(unit, 1, persona, out_dir)
        results.append((unit, r))

    # Summary
    print(f"\n{'='*60}")
    print("GENERATION COMPLETE")
    print(f"{'='*60}")
    for unit, r in results:
        status = "OK" if r else "FAIL"
        title = r.title if r else "?"
        print(f"  [{status}] {unit.grade_level} {unit.subject}: {title}")

    # List all files
    print(f"\nOutput directory: {base_dir}")
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            fp = os.path.join(root, f)
            size = os.path.getsize(fp)
            print(f"  {os.path.relpath(fp, base_dir)} ({size:,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
