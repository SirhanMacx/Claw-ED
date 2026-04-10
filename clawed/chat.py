"""Student chatbot engine — answers questions in the teacher's voice."""

from __future__ import annotations

from typing import Any

from clawed.llm import LLMClient
from clawed.models import AppConfig, TeacherPersona


async def student_chat(
    question: str,
    lesson_json: dict[str, Any],
    persona: TeacherPersona,
    chat_history: list[dict[str, str]] | None = None,
    config: AppConfig | None = None,
) -> str:
    """Answer a student question using the lesson context and teacher persona.

    Args:
        question: The student's question.
        lesson_json: The current lesson data (dict from JSON).
        persona: The teacher persona for voice/style.
        chat_history: Optional prior messages [{"role": "user"|"assistant", "content": "..."}].
        config: Optional app config override.

    Returns:
        The chatbot's response in the teacher's voice.
    """
    # Build lesson context
    title = lesson_json.get("title", "Untitled Lesson")
    objective = lesson_json.get("objective", "")
    do_now = lesson_json.get("do_now", "")
    direct_instruction = lesson_json.get("direct_instruction", "")
    guided_practice = lesson_json.get("guided_practice", "")
    independent_work = lesson_json.get("independent_work", "")
    standards = lesson_json.get("standards", [])

    exit_ticket = lesson_json.get("exit_ticket", [])
    et_text = "\n".join(f"- {q['question']}" for q in exit_ticket if isinstance(q, dict)) if exit_ticket else "None"

    lesson_context = (
        f"Lesson: {title}\n"
        f"Objective: {objective}\n"
        f"Standards: {', '.join(standards) if standards else 'None'}\n\n"
        f"Do-Now: {do_now[:300]}\n\n"
        f"Direct Instruction:\n{direct_instruction[:800]}\n\n"
        f"Guided Practice:\n{guided_practice[:500]}\n\n"
        f"Independent Work:\n{independent_work[:300]}\n\n"
        f"Exit Ticket Questions:\n{et_text}\n"
    )

    # Build chat history context
    history_text = ""
    if chat_history:
        recent = chat_history[-6:]  # Last 6 messages for context
        parts = []
        for msg in recent:
            role_label = "Student" if msg["role"] == "user" else "Teacher"
            parts.append(f"{role_label}: {msg['content']}")
        history_text = "\nRecent conversation:\n" + "\n".join(parts) + "\n"

    system_prompt = (
        f"You are a helpful AI tutor responding in this teacher's voice and style.\n\n"
        f"{persona.to_prompt_context()}\n\n"
        f"INSTRUCTIONS:\n"
        f"- Answer the student's question about the current lesson.\n"
        f"- Use {persona.name}'s tone: {persona.tone}.\n"
        f"- Match the vocabulary level: {persona.vocabulary_level.value.replace('_', ' ')}.\n"
        f"- If the question is off-topic, gently redirect to the lesson.\n"
        f"- Offer to explain differently or give examples if the student seems confused.\n"
        f"- Keep responses concise but thorough (2-4 paragraphs max).\n"
        f"- Never reveal that you are an AI — respond as if you are the teacher.\n"
    )

    prompt = (
        f"## Current Lesson Context\n{lesson_context}\n"
        f"{history_text}\n"
        f"## Student's Question\n{question}\n\n"
        f"Respond as {persona.name} would, using the lesson content to inform your answer."
    )

    client = LLMClient(config)
    return await client.generate(
        prompt=prompt,
        system=system_prompt,
        temperature=0.6,
        max_tokens=1500,
    )
