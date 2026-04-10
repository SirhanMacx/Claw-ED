"""Audio lesson generation — TTS-ready narration scripts and MP3 export.

Converts teacher_script fields from MasterContent into structured narration
that can be:
1. Pasted into any TTS tool (ElevenLabs, OpenAI TTS, Google TTS)
2. Directly rendered via OpenAI TTS API if configured
3. Used as a podcast-style lesson overview

No external dependencies required for script generation. TTS API calls
are optional and require an API key.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clawed.master_content import MasterContent

logger = logging.getLogger(__name__)


def compile_narration_script(master: "MasterContent", output_dir: Path) -> Path:
    """Generate a TTS-ready narration script from a MasterContent lesson.

    The script is structured for natural reading:
    - Clear section breaks with pause markers [PAUSE]
    - Conversational tone derived from teacher_script fields
    - Hook → Content → Key Points → Review → Closing flow

    Args:
        master: The MasterContent source object.
        output_dir: Directory for the output file.

    Returns:
        Path to the generated narration script (.txt).
    """
    from clawed.io import safe_filename

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    # Opening
    personality = getattr(master, "lesson_personality", "")
    if personality:
        lines.append(f"{personality}")
        lines.append("[PAUSE]")

    lines.append(f"Welcome to today's lesson: {master.title or 'today'}.")
    topic_text = master.topic or "today's topic"
    subject_text = master.subject or "class"
    grade_text = master.grade_level or "your grade"
    lines.append(f"We're covering {topic_text} in {subject_text}, {grade_text}.")
    lines.append(f"Our objective: {master.objective}")
    lines.append("[PAUSE]")

    # Vocabulary preview
    if master.vocabulary:
        lines.append("Let's start with some key vocabulary you'll need today.")
        for entry in master.vocabulary[:5]:
            lines.append(f"{entry.term} means {entry.definition}. For example: {entry.context_sentence}")
            lines.append("[PAUSE]")

    # Direct instruction (from teacher_script — the most natural voice)
    for section in master.direct_instruction:
        hook = getattr(section, "hook", "")
        if hook:
            lines.append(hook)
            lines.append("[PAUSE]")

        lines.append(f"Now let's talk about: {section.heading}.")
        lines.append("[PAUSE]")

        # Use teacher_script if available — it's the most natural text
        if section.teacher_script:
            lines.append(section.teacher_script)
        else:
            lines.append(section.content)
        lines.append("[PAUSE]")

        if section.key_points:
            lines.append("The key points to remember:")
            for kp in section.key_points:
                lines.append(f"  {kp}")
            lines.append("[PAUSE]")

        transition = getattr(section, "transition", "")
        if transition:
            lines.append(transition)
            lines.append("[PAUSE]")

    # Exit ticket preview
    if master.exit_ticket:
        lines.append("Before we wrap up, here's what you'll need to show me you learned today.")
        for i, et in enumerate(master.exit_ticket, 1):
            lines.append(f"Question {i}: {et.question}")
        lines.append("[PAUSE]")

    # Closing
    lines.append("That's our lesson for today. Review your guided notes, and come ready to build on this tomorrow.")
    if master.homework and master.homework.strip():
        lines.append(f"For homework: {master.homework}")

    safe = safe_filename(master.title)
    out_path = output_dir / f"{safe}_narration.txt"
    out_path.write_text("\n\n".join(lines), encoding="utf-8")

    logger.info("Narration script saved to %s", out_path)
    return out_path


async def compile_audio_mp3(
    master: "MasterContent",
    output_dir: Path,
    voice: str = "alloy",
) -> Path | None:
    """Generate an MP3 audio file from the lesson using OpenAI TTS.

    Requires OPENAI_API_KEY to be configured. Falls back to generating
    a narration script if TTS is not available.

    Args:
        master: The MasterContent source object.
        output_dir: Directory for the output file.
        voice: OpenAI TTS voice (alloy, echo, fable, onyx, nova, shimmer).

    Returns:
        Path to the MP3 file, or None if TTS is not available.
    """
    # First generate the script
    script_path = compile_narration_script(master, output_dir)
    script_text = script_path.read_text(encoding="utf-8")

    # Clean up for TTS — remove pause markers, keep natural flow
    tts_text = script_text.replace("[PAUSE]", ". ").replace("\n\n", " ")
    # Trim to TTS API limits (4096 chars for OpenAI)
    if len(tts_text) > 4000:
        tts_text = tts_text[:4000] + "... That's a summary of today's lesson."

    try:
        from clawed.config import get_api_key

        api_key = get_api_key("openai")
        if not api_key:
            logger.info("No OpenAI key — narration script saved but no MP3 generated")
            return None

        import httpx

        from clawed.io import safe_filename

        output_dir = Path(output_dir)
        safe = safe_filename(master.title)
        mp3_path = output_dir / f"{safe}_audio.mp3"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "tts-1",
                    "voice": voice,
                    "input": tts_text,
                },
            )
            resp.raise_for_status()
            mp3_path.write_bytes(resp.content)

        logger.info("Audio lesson saved to %s", mp3_path)
        return mp3_path

    except Exception as exc:
        logger.info("TTS generation failed (%s) — narration script still available", exc)
        return None
