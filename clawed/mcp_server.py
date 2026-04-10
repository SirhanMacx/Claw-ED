"""Claw-ED MCP Server — expose teaching tools via Model Context Protocol.

This lets Claude Code, Hermes Agent, Claude Desktop, and other MCP clients
call Claw-ED tools directly: search curriculum, query the knowledge graph,
generate lessons, plan units, ingest materials, answer student questions,
and look up standards.

Uses stdio transport (the MCP standard). The client process spawns this
server and communicates over stdin/stdout.

v4.7.2026.5: Added curriculum search, knowledge graph queries, session
history, and wiki query tools. Large results use maxResultSizeChars
annotation (Claude Code 2.1.91+) for up to 500K chars.

Usage:
    clawed mcp-server
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Claw-ED",
    instructions=(
        "Claw-ED is an AI teaching assistant with a knowledge base of the "
        "teacher's own curriculum files. Use search_curriculum to find relevant "
        "materials, query_knowledge_graph for topic relationships, and "
        "generate_lesson or generate_unit to create content in the teacher's voice."
    ),
)

# Default teacher_id for MCP (single-teacher local mode)
_DEFAULT_TEACHER = "default"


# ── Curriculum search ────────────────────────────────────────────────


@mcp.tool()
async def search_curriculum(
    query: str,
    top_k: int = 10,
    teacher_id: str = _DEFAULT_TEACHER,
) -> str:
    """Search the teacher's ingested curriculum materials by topic or keyword.

    Returns the most relevant chunks from the teacher's own lesson plans,
    slideshows, handouts, and other uploaded materials. Use this to ground
    lesson generation in the teacher's existing work.

    Args:
        query: What to search for (e.g., "causes of the French Revolution")
        top_k: Max results to return (1-50, default 10)
        teacher_id: Teacher ID (default for single-teacher setups)
    """
    from clawed.agent_core.memory.curriculum_kb import CurriculumKB

    kb = CurriculumKB()
    results = kb.search(teacher_id, query, top_k=min(top_k, 50))

    if not results:
        return json.dumps({"results": [], "message": "No matching materials found."})

    output = []
    for r in results:
        output.append(
            {
                "doc_title": r.get("doc_title", ""),
                "chunk_text": r.get("chunk_text", ""),
                "similarity": round(r.get("similarity", 0), 3),
                "source_path": r.get("source_path", ""),
            }
        )

    return json.dumps({"results": output, "count": len(output)}, indent=2)


# ── Knowledge graph ──────────────────────────────────────────────────


@mcp.tool()
async def query_knowledge_graph(
    topic: str,
    teacher_id: str = _DEFAULT_TEACHER,
) -> str:
    """Query the curriculum knowledge graph for topic relationships.

    Returns prerequisites, related topics, standards alignments, and
    vocabulary for a curriculum topic. Built from the teacher's ingested
    materials — reflects their actual curriculum structure.

    Args:
        topic: Topic to query (e.g., "Reconstruction", "photosynthesis")
        teacher_id: Teacher ID (default for single-teacher setups)
    """
    from clawed.agent_core.memory.knowledge_graph import CurriculumKG

    kg = CurriculumKG()

    # Get formatted topic context
    context = kg.get_topic_context(teacher_id, topic)

    # Get entity details if exists
    entity = kg.query_entity(teacher_id, topic)

    # Get all related entities
    related = kg.query_related(teacher_id, topic)

    result = {
        "topic": topic,
        "context": context or "No knowledge graph data for this topic.",
        "entity": entity,
        "relationships": related[:20],
    }

    # Get prerequisites specifically
    prereqs = kg.get_prerequisites(teacher_id, topic)
    if prereqs:
        result["prerequisites"] = [p["entity"] for p in prereqs]

    # Stats
    stats = kg.stats(teacher_id)
    result["kg_stats"] = stats

    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def kg_stats(teacher_id: str = _DEFAULT_TEACHER) -> str:
    """Get knowledge graph statistics — entity count, triple count, types.

    Args:
        teacher_id: Teacher ID (default for single-teacher setups)
    """
    from clawed.agent_core.memory.knowledge_graph import CurriculumKG

    kg = CurriculumKG()
    return json.dumps(kg.stats(teacher_id), indent=2)


# ── Session history ──────────────────────────────────────────────────


@mcp.tool()
async def search_session_history(
    query: str,
    top_k: int = 5,
    teacher_id: str = _DEFAULT_TEACHER,
) -> str:
    """Search compressed past teaching sessions by topic.

    Returns summaries of past sessions that discussed similar topics,
    including materials generated, decisions made, and feedback given.

    Args:
        query: What to search for in past sessions
        top_k: Max results (1-20, default 5)
        teacher_id: Teacher ID
    """
    from clawed.agent_core.memory.session_compress import (
        search_session_history as _search,
    )

    results = _search(teacher_id, query, top_k=min(top_k, 20))

    if not results:
        return json.dumps({"results": [], "message": "No matching past sessions."})

    output = []
    for r in results:
        output.append(
            {
                "session_date": r.get("session_date", ""),
                "turn_count": r.get("turn_count", 0),
                "topics": json.loads(r.get("topics", "[]")),
                "materials_generated": json.loads(r.get("materials_generated", "[]")),
                "summary": r.get("compressed_text", ""),
                "similarity": round(r.get("similarity", 0), 3),
            }
        )

    return json.dumps({"results": output, "count": len(output)}, indent=2)


# ── Wiki ─────────────────────────────────────────────────────────────


@mcp.tool()
async def query_wiki(
    question: str,
    teacher_id: str = _DEFAULT_TEACHER,
) -> str:
    """Ask a question answered from the teacher's compiled curriculum wiki.

    The wiki is built from ingested materials — structured articles synthesized
    from the teacher's own lesson plans, slideshows, and handouts. Returns
    a cited answer with source articles.

    Args:
        question: Question to answer from the wiki
        teacher_id: Teacher ID
    """
    from clawed.wiki import query_wiki as _query

    result = _query(teacher_id, question)
    return json.dumps(
        {
            "answer": result.answer,
            "sources": result.sources,
            "articles_read": result.articles_read,
        },
        indent=2,
        default=str,
    )


# ── Lesson generation ────────────────────────────────────────────────


@mcp.tool()
async def generate_lesson(
    topic: str,
    grade: str = "8",
    subject: str = "General",
    persona_path: str = "",
) -> str:
    """Generate a complete daily lesson plan in the teacher's voice.

    Args:
        topic: The lesson topic (e.g., "photosynthesis", "fractions")
        grade: Grade level (e.g., "8", "K", "11")
        subject: Subject area (e.g., "Science", "Math", "History")
        persona_path: Optional path to persona JSON file
    """
    from clawed.lesson import generate_lesson as gen_lesson
    from clawed.models import AppConfig, LessonBrief, TeacherPersona, UnitPlan

    config = AppConfig.load()
    persona = TeacherPersona()

    if persona_path:
        from pathlib import Path

        p = Path(persona_path).expanduser()
        if p.exists():
            persona = TeacherPersona.model_validate_json(p.read_text(encoding="utf-8"))

    # Create minimal unit context for standalone lesson
    unit = UnitPlan(
        title=f"{topic} Unit",
        subject=subject,
        grade_level=grade,
        topic=topic,
        duration_weeks=1,
        overview=f"A lesson on {topic}.",
        daily_lessons=[LessonBrief(lesson_number=1, topic=topic, description=f"Introduction to {topic}")],
    )

    lesson = await gen_lesson(lesson_number=1, unit=unit, persona=persona, config=config)
    return lesson.model_dump_json(indent=2)


@mcp.tool()
async def generate_unit(
    topic: str,
    grade: str = "8",
    subject: str = "General",
    weeks: int = 2,
) -> str:
    """Generate a multi-week unit plan with daily lesson sequence.

    Args:
        topic: The unit topic (e.g., "American Revolution", "Ecosystems")
        grade: Grade level
        subject: Subject area
        weeks: Duration in weeks (1-6)
    """
    from clawed.models import AppConfig, TeacherPersona
    from clawed.planner import plan_unit

    config = AppConfig.load()
    persona = TeacherPersona()

    unit = await plan_unit(
        subject=subject,
        grade_level=grade,
        topic=topic,
        duration_weeks=weeks,
        persona=persona,
        config=config,
    )
    return unit.model_dump_json(indent=2)


# ── Ingestion ────────────────────────────────────────────────────────


@mcp.tool()
async def ingest_materials(path: str) -> str:
    """Ingest teaching materials and extract a teacher persona.

    Args:
        path: Path to a directory, ZIP file, or single file containing teaching materials
    """
    from pathlib import Path as _Path

    from clawed.ingestor import ingest_path
    from clawed.models import AppConfig
    from clawed.persona import extract_persona

    source = _Path(path).expanduser().resolve()
    docs = ingest_path(source)

    if not docs:
        return json.dumps({"error": "No supported documents found", "path": str(source)})

    config = AppConfig.load()
    persona = await extract_persona(docs, config)

    return json.dumps(
        {
            "documents_ingested": len(docs),
            "persona": json.loads(persona.model_dump_json()),
        },
        indent=2,
    )


# ── Student Q&A ──────────────────────────────────────────────────────


@mcp.tool()
async def student_question(
    question: str,
    class_code: str,
    student_id: str = "mcp-student",
) -> str:
    """Answer a student question using the active lesson context and teacher's voice.

    Args:
        question: The student's question about the lesson
        class_code: The class code provided by the teacher
        student_id: Optional student identifier
    """
    from clawed.student_bot import StudentBot

    bot = StudentBot()
    answer = await bot.handle_message(question, student_id, class_code)
    return answer


# ── Standards ────────────────────────────────────────────────────────


@mcp.tool()
async def get_teacher_standards(
    state: str = "",
    subjects: str = "",
    grades: str = "",
) -> str:
    """Look up education standards for a teacher's state, subjects, and grades.

    Args:
        state: US state abbreviation (e.g., "NY", "CA", "TX")
        subjects: Comma-separated subjects (e.g., "math,science")
        grades: Comma-separated grade levels (e.g., "7,8")
    """
    from clawed.state_standards import get_standards_context_for_prompt

    subject_list = [s.strip() for s in subjects.split(",") if s.strip()] if subjects else []
    grade_list = [g.strip() for g in grades.split(",") if g.strip()] if grades else []

    if not state:
        return json.dumps({"error": "State abbreviation required (e.g., 'NY', 'CA')"})

    context = get_standards_context_for_prompt(state, subject_list, grade_list)
    return context if context else json.dumps({"message": f"No standards data for state={state}"})


def run_server() -> None:
    """Run the MCP server using stdio transport (the standard MCP transport)."""
    mcp.run(transport="stdio")
