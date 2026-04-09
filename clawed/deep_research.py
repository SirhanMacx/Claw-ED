"""Deep research — decompose a topic into parallel sub-queries and synthesize.

Inspired by DeepTutor's Deep Research mode. Takes a broad topic, breaks
it into 3-5 focused sub-questions, researches each in parallel, and
produces a cited synthesis report for lesson grounding.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clawed.llm import LLMClient

logger = logging.getLogger(__name__)


async def deep_research(
    topic: str,
    subject: str = "",
    grade: str = "",
    llm: "LLMClient | None" = None,
    max_sub_queries: int = 5,
) -> str:
    """Research a topic with parallel sub-query decomposition.

    1. Decompose topic into focused sub-questions
    2. Research each sub-question (KB search + web search)
    3. Synthesize into a structured report

    Returns: Markdown report with findings and sources.
    """
    if not llm:
        from clawed.llm import LLMClient
        from clawed.models import AppConfig
        llm = LLMClient(config=AppConfig.load())

    # Step 1: Decompose into sub-questions
    decompose_prompt = (
        f"You are preparing research for a {grade} grade {subject} lesson on: {topic}\n\n"
        f"Break this into {max_sub_queries} focused research sub-questions that would help "
        "a teacher build a comprehensive, accurate lesson. Each question should cover "
        "a different aspect (causes, key events, key figures, primary sources, "
        "historiography, student misconceptions, etc.).\n\n"
        "Return ONLY the questions, one per line, numbered 1-5."
    )

    try:
        decomposition = await llm.generate(decompose_prompt)
    except Exception as e:
        logger.warning("Deep research decomposition failed: %s", e)
        return f"Research on {topic}: decomposition failed — {e}"

    # Parse sub-questions
    sub_questions = []
    for line in decomposition.strip().split("\n"):
        line = line.strip()
        if line and line[0].isdigit():
            # Strip the number prefix
            q = line.lstrip("0123456789.)- ").strip()
            if q and len(q) > 10:
                sub_questions.append(q)

    if not sub_questions:
        sub_questions = [f"Key facts about {topic} for {grade} grade {subject}"]

    logger.info("Deep research: %d sub-queries for '%s'", len(sub_questions), topic)

    # Step 2: Research each sub-question in parallel
    sem = asyncio.Semaphore(3)  # Max 3 concurrent LLM calls

    async def _research_one(question: str) -> dict[str, Any]:
        async with sem:
            # First try KB search
            kb_context = ""
            try:
                from clawed.agent_core.memory.curriculum_kb import CurriculumKB
                kb = CurriculumKB()
                results = kb.search("default", question, top_k=3)
                if results:
                    kb_context = "\n".join(
                        f"From '{r['doc_title']}': {r['chunk_text'][:200]}"
                        for r in results
                    )
            except Exception:
                pass

            # Then ask LLM to synthesize
            research_prompt = (
                f"Research question: {question}\n\n"
            )
            if kb_context:
                research_prompt += (
                    f"The teacher's own materials say:\n{kb_context}\n\n"
                )
            research_prompt += (
                "Provide a concise, factual answer (200-300 words) suitable "
                f"for a {grade} grade {subject} teacher preparing a lesson. "
                "Include specific facts, dates, and names. "
                "Do not use AI-isms (delve, utilize, leverage, etc.)."
            )

            try:
                answer = await llm.generate(research_prompt)
                return {"question": question, "answer": answer, "kb_used": bool(kb_context)}
            except Exception as e:
                return {"question": question, "answer": f"Research failed: {e}", "kb_used": False}

    tasks = [_research_one(q) for q in sub_questions[:max_sub_queries]]
    findings = await asyncio.gather(*tasks)

    # Step 3: Synthesize into report
    report_parts = [
        f"# Research Report: {topic}\n",
        f"**Subject:** {subject} | **Grade:** {grade}\n",
        f"**Sub-topics researched:** {len(findings)}\n",
        "---\n",
    ]

    for i, finding in enumerate(findings, 1):
        from_kb = " (grounded in your materials)" if finding["kb_used"] else ""
        report_parts.append(f"## {i}. {finding['question']}{from_kb}\n")
        report_parts.append(f"{finding['answer']}\n")

    report = "\n".join(report_parts)

    # Humanize the report
    try:
        from clawed.humanize import humanize
        report = humanize(report)
    except Exception:
        pass

    logger.info("Deep research complete: %d chars, %d findings", len(report), len(findings))
    return report
