"""Compile interactive HTML learning games from lesson content.

Every game is unique — the LLM designs the mechanic, visuals, and
interaction based on the lesson content, teacher's style, and student
preferences. No templates. No repetition.

The compiler:
1. Extracts game-worthy content from MasterContent
2. Asks the LLM to design and code a complete single-file HTML game
3. Validates the output (loads, contains educational content)
4. Falls back to regeneration if the game is broken

Usage:
    from clawed.compile_game import compile_game
    path = await compile_game(master, persona, output_dir)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from clawed.io import safe_filename
from clawed.llm import LLMClient
from clawed.master_content import MasterContent
from clawed.model_router import route as route_model
from clawed.models import AppConfig, TeacherPersona

logger = logging.getLogger(__name__)

GAME_SYSTEM_PROMPT = """\
You are an expert educational game developer. You create single-file HTML \
games that teach through play. Every game you make is UNIQUE — different \
mechanic, different visual style, different interaction pattern.

RULES:
- Output ONLY the complete HTML file. No explanation, no markdown fencing.
- The file MUST start with <!DOCTYPE html> then <html>, then <head>, then <body>. \
Always use this exact structure — never put CSS or text directly inside <html> \
without a <head> or <body> wrapper.
- The <head> MUST contain: <meta charset="UTF-8">, a <title> tag, and a <style> block.
- The <body> contains all visible elements and <script> tags.
- The file must be self-contained: all CSS and JS inline.
- You may use a Three.js CDN link for 3D: \
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
- The game MUST work on phones, tablets, Chromebooks (responsive, touch).
- The game MUST be genuinely FUN — not a boring quiz with buttons.
- Include scoring, feedback, progression (levels or rounds).
- Include a start screen with the lesson title and instructions.
- Include an end screen with score and "play again" button.
- ALL educational content must be embedded as data in the JS.
- Add a small footer: "Made with Claw-ED — github.com/SirhanMacx/Claw-ED"

VISUALS — DO NOT USE IMAGE FILES. Create ALL visuals programmatically:
- Use Three.js for immersive 3D scenes themed to the lesson content. \
  Age of Exploration = 3D ocean with ships. Civil War = battlefields. \
  Renaissance = marble halls. Science = molecular structures.
- Use CSS gradients, animations, box-shadows, and transforms for 2D polish.
- Use HTML Canvas for custom diagrams, maps, or illustrations.
- Use CSS shapes and emoji for icons — never <img> tags.
- Use SVG inline for any detailed graphics (maps, diagrams, symbols).
- The game should feel IMMERSIVE — like the student is inside the topic, \
  not reading a quiz. 3D environments, particle effects, ambient animation.
- Go ABOVE AND BEYOND visually. This should look like a real game, not a \
  school worksheet with buttons.

ACCESSIBILITY (required — students with disabilities must be able to play):
- Game MUST support keyboard-only navigation (no mouse required).
- Add ARIA labels to all interactive elements.
- Use minimum 4.5:1 color contrast ratio for all text.
- Include a 'Skip to main content' link as the first focusable element.
- All images must have descriptive alt text.
- Timer-based activities must have a pause button.

WHAT MAKES A GREAT LEARNING GAME:
- The mechanic TEACHES, not just tests. Students learn through the gameplay.
- Wrong answers give feedback that explains WHY it's wrong.
- Difficulty progresses — start easy, get harder.
- Visual and audio feedback (CSS animations, color changes, shake effects).
- Time pressure is optional but adds excitement when appropriate.
- Multiplayer/competitive elements are great if they fit.
"""


def _extract_game_content(master: MasterContent) -> str:
    """Extract educational content from MasterContent for game generation.

    Accepts MasterContent or DailyLesson (single-agent path lacks subject/grade_level).
    """
    parts = [
        f"LESSON: {master.title}",
        f"SUBJECT: {getattr(master, 'subject', 'Social Studies')}",
        f"GRADE: {getattr(master, 'grade_level', '')}",
        f"TOPIC: {getattr(master, 'topic', master.title)}",
        f"OBJECTIVE: {master.objective}",
    ]

    if master.vocabulary:
        parts.append("\nVOCABULARY:")
        for v in master.vocabulary:
            parts.append(
                f"  - {v.term}: {v.definition}"
                + (f" (context: {v.context_sentence})" if v.context_sentence else "")
            )

    guided_notes = getattr(master, "guided_notes", None)
    if guided_notes:
        parts.append("\nKEY FACTS (fill-in-the-blank):")
        for note in guided_notes:
            parts.append(f"  - Q: {note.prompt} → A: {note.answer}")

    exit_ticket = getattr(master, "exit_ticket", None)
    if exit_ticket:
        parts.append("\nQUIZ QUESTIONS:")
        # DailyLesson exit_ticket is a list of ExitTicketQuestion (has .question)
        # MasterContent exit_ticket may differ — handle both
        for i, q in enumerate(exit_ticket if isinstance(exit_ticket, list) else [], 1):
            question_text = getattr(q, "question", str(q))
            parts.append(f"  {i}. {question_text}")
            if hasattr(q, "expected_answer") and q.expected_answer:
                parts.append(f"     Answer: {q.expected_answer}")

    primary_sources = getattr(master, "primary_sources", None)
    if primary_sources:
        parts.append("\nPRIMARY SOURCES:")
        for src in primary_sources:
            src_title = getattr(src, "title", str(src))
            src_type = getattr(src, "source_type", "")
            parts.append(f"  - {src_title} ({src_type})")
            if hasattr(src, "content_text") and src.content_text:
                parts.append(f"    Text: {src.content_text[:300]}...")

    direct_instruction = getattr(master, "direct_instruction", None)
    if direct_instruction and not isinstance(direct_instruction, str):
        parts.append("\nKEY CONCEPTS:")
        for section in direct_instruction:
            parts.append(f"  - {getattr(section, 'heading', str(section))}")
            if hasattr(section, "key_points") and section.key_points:
                for pt in section.key_points[:3]:
                    parts.append(f"    • {pt}")
    elif isinstance(direct_instruction, str) and direct_instruction:
        parts.append(f"\nKEY CONCEPTS:\n{direct_instruction[:500]}")

    return "\n".join(parts)


def _repair_html_structure(html: str) -> str:
    """Repair common LLM HTML generation failures.

    LLMs sometimes emit:
    - CSS rules directly after <!DOCTYPE html> with no <head> or <body>
    - <title> text as bare text instead of inside a <title> tag
    - <style> content without the wrapping <style> tag
    - Missing </html> closer

    This function detects those patterns and wraps the content into a
    valid HTML skeleton, preserving all the CSS and JS the LLM generated.
    """
    html_lower = html.lower()

    # Strip duplicate DOCTYPE/html tags (LLM sometimes nests two documents)
    if html.count("<!DOCTYPE") > 1:
        # Keep only the content between the LAST <!DOCTYPE and end
        # Actually: strip all but the first DOCTYPE
        parts = html.split("<!DOCTYPE")
        html = "<!DOCTYPE" + parts[1]  # keep first occurrence + content
        for extra in parts[2:]:
            # Append content after stripping the duplicate preamble
            extra_content = re.sub(
                r"^[^>]*>\s*<html[^>]*>\s*", "", extra, flags=re.IGNORECASE
            )
            html += extra_content
        html_lower = html.lower()

    # Check for bare JS not wrapped in <script> tags
    has_script_tags = "<script" in html_lower
    has_js_code = bool(re.search(
        r"(?:function\s+\w+|const\s+\w+\s*=|let\s+\w+\s*=|document\.|addEventListener)",
        html
    ))
    if not has_script_tags and has_js_code:
        # Find where JS starts (after the last </div> or after CSS)
        # Look for first function/const/let/document line
        js_start = re.search(
            r"\n((?:function |const |let |var |document\.|//\s*[-=]|class\s+\w+\s*\{))",
            html
        )
        if js_start:
            before_js = html[:js_start.start()]
            js_code = html[js_start.start():]
            # Strip trailing </body></html> from JS if present
            js_code = re.sub(r"\s*</body>\s*</html>\s*$", "", js_code, flags=re.IGNORECASE)
            html = before_js + "\n<script>\n" + js_code + "\n</script>\n</body>\n</html>"
            html_lower = html.lower()

    # Already well-formed — has <head>, <body>, and <script>
    if "<head>" in html_lower and "<body>" in html_lower and (has_script_tags or "<script" in html_lower):
        return html

    # Has <head> but no <body> — unusual, leave it
    if "<head>" in html_lower:
        return html

    # Missing <head>/<body> — LLM dumped CSS/JS straight into <html>
    # Strategy: find the first <script or first element tag to split on,
    # put everything before the first block element into <head>,
    # everything else into <body>.

    # Collect lines after <!DOCTYPE html><html ...>
    # Find where the html tag ends
    html_tag_end = html_lower.find(">", html_lower.find("<html"))
    if html_tag_end == -1:
        # No <html> tag at all — wrap everything
        title_match = re.search(r"^([^\n<@{]+)", html.strip())
        title_text = title_match.group(1).strip() if title_match else "Learning Game"
        return (
            f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
            f"<meta charset=\"UTF-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"<title>{title_text}</title>\n"
            f"<style>\n{html}\n</style>\n</head>\n<body></body>\n</html>"
        )

    _preamble = html[:html_tag_end + 1]  # noqa: F841  # everything up to and including <html ...>
    rest = html[html_tag_end + 1:].strip()

    # Extract bare title text (first non-tag, non-CSS line after <html>)
    # This catches lines like "Age of Exploration: Chart Your Course" emitted before the CSS
    title_text = "Learning Game"
    title_match = re.match(r"^\s*([A-Za-z][^\n@{<]{3,120})\n", rest)
    if title_match:
        candidate = title_match.group(1).strip()
        # Accept as title if it looks like a human-readable title (not CSS)
        if not candidate.startswith(("@", "{", ".", "#", "*", ":", "/")):
            title_text = candidate
            rest = rest[title_match.end():]

    # Split: CSS/meta goes in <head>, script/div/etc goes in <body>
    head_parts: list[str] = []
    body_parts: list[str] = []  # noqa: F841

    # Collect <meta> tags floating outside <head>
    meta_tags = re.findall(r"<meta[^>]*>", rest, re.IGNORECASE)
    for m in meta_tags:
        head_parts.append(m)
        rest = rest.replace(m, "", 1)

    # Wrap bare CSS (starts with @import, :root, or selector{) in <style>
    # Find contiguous CSS blocks before the first <script or <div
    first_script = re.search(r"<script|<div|<section|<main|<canvas", rest, re.IGNORECASE)
    split_at = first_script.start() if first_script else len(rest)

    css_block = rest[:split_at].strip()
    body_block = rest[split_at:].strip()

    if css_block:
        # Check if it's raw CSS (no surrounding <style> tags)
        if not re.search(r"<style", css_block, re.IGNORECASE):
            head_parts.append(f"<style>\n{css_block}\n</style>")
        else:
            head_parts.append(css_block)

    head_html = "\n".join(head_parts)
    body_html = body_block

    # Ensure </html> at end
    if not body_html.rstrip().endswith("</html>"):
        body_html = body_html.rstrip()
        if not body_html.endswith("</body>"):
            body_html += "\n</body>"
        body_html += "\n</html>"

    repaired = (
        f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        f"<meta charset=\"UTF-8\">\n"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, user-scalable=no\">\n"
        f"<title>{title_text}</title>\n"
        f"{head_html}\n"
        f"</head>\n<body>\n"
        f"{body_html}"
    )

    logger.info("Repaired HTML structure (was missing <head>/<body>)")
    return repaired


def _validate_game_html(html: str, master: MasterContent) -> list[str]:
    """Validate that the generated HTML is a working game."""
    issues = []

    if not html or len(html) < 500:
        issues.append("HTML is too short to be a real game")

    if "<html" not in html.lower():
        issues.append("Missing <html> tag")

    if "<head>" not in html.lower():
        issues.append("Missing <head> tag — CSS may render broken")

    if "<body>" not in html.lower():
        issues.append("Missing <body> tag — content structure invalid")

    if "<script" not in html.lower():
        issues.append("Missing <script> tag — no JavaScript")

    if "function" not in html and "=>" not in html:
        issues.append("No JavaScript functions found")

    # Check that educational content is embedded
    topic_words = getattr(master, "topic", master.title).lower().split()[:3]
    html_lower = html.lower()
    found_topic = any(w in html_lower for w in topic_words if len(w) > 3)
    if not found_topic:
        issues.append(
            f"Topic words ({', '.join(topic_words)}) not found in game"
        )

    if master.vocabulary:
        first_term = master.vocabulary[0].term.lower()
        if first_term not in html_lower:
            issues.append(
                f"First vocabulary term '{first_term}' not in game"
            )

    return issues


async def compile_game(
    master: "MasterContent | Any",
    persona: TeacherPersona | None = None,
    output_dir: Path | None = None,
    config: AppConfig | None = None,
    student_preferences: str = "",
    game_style: str = "",
) -> Path:
    """Generate a unique interactive HTML game from lesson content.

    The LLM designs the game mechanic, visuals, and interaction from
    scratch every time. No templates.

    Args:
        master: The lesson's MasterContent (source of truth).
        persona: Teacher persona for voice/style matching.
        output_dir: Where to save the .html file.
        config: App config for model routing.
        student_preferences: What students are into ("they love Among Us",
            "obsessed with Minecraft", "competitive, love team challenges").
        game_style: Specific game style request ("jeopardy", "escape room",
            "battle royale quiz", etc.). If empty, LLM decides.

    Returns:
        Path to the generated .html game file.
    """
    if output_dir is None:
        from clawed.io import output_dir as get_output_dir
        output_dir = get_output_dir()
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = config or AppConfig.load()
    # Route to DEEP tier within the teacher's chosen provider.
    # Teacher picked Ollama? Gets their best Ollama model.
    # Teacher picked Anthropic? Gets Opus. Their choice.
    config = route_model("game_generate", config)

    # Game generation requires code-capable models. Warn if using a model
    # that is known to produce broken HTML (small local Ollama models).
    code_weak_models = {"qwen3.5:cloud", "llama3.2:latest", "phi3:latest"}
    resolved_model = getattr(config, "ollama_model", "") or ""
    if resolved_model in code_weak_models:
        logger.warning(
            "Game generation works best with code-capable models. "
            "Model '%s' may produce broken HTML. Consider using a larger "
            "model (minimax, deepseek-coder, codestral) or a cloud provider "
            "(Anthropic, OpenAI) for games.",
            resolved_model,
        )

    client = LLMClient(config)

    # Build the game generation prompt
    content = _extract_game_content(master)

    prompt_parts = [
        "Design and code a COMPLETE, UNIQUE, single-file HTML learning "
        "game for this lesson.\n",
        content,
    ]

    if student_preferences:
        prompt_parts.append(
            f"\nSTUDENT PREFERENCES: {student_preferences}\n"
            "Design the game mechanic to match what these students enjoy. "
            "If they like a specific game, use a similar mechanic but "
            "with educational content."
        )

    if game_style:
        prompt_parts.append(
            f"\nREQUESTED STYLE: {game_style}\n"
            "Use this style as inspiration but make it your own."
        )
    else:
        prompt_parts.append(
            "\nNo specific style requested — surprise me. Be creative. "
            "Pick a game mechanic that FITS this specific lesson content. "
            "A timeline lesson should have different gameplay than a "
            "vocabulary lesson. Think about what mechanic actually helps "
            "students LEARN this material."
        )

    if persona:
        prompt_parts.append(
            f"\nTEACHER'S STYLE: {persona.tone or 'engaging'}\n"
            f"Grade level: {getattr(master, 'grade_level', '')}\n"
            "Match the difficulty and humor to this teacher and grade."
        )

    prompt = "\n".join(prompt_parts)

    # Generate with retry
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            html = await client.generate(
                prompt=prompt,
                system=GAME_SYSTEM_PROMPT,
                temperature=0.8,  # Creative — we want variety
                max_tokens=12000,
            )

            # Clean: strip markdown fencing if present
            html = html.strip()
            if html.startswith("```"):
                html = re.sub(r"^```\w*\n?", "", html)
                html = re.sub(r"\n?```$", "", html)
            html = html.strip()

            # Structural repair: LLMs sometimes emit CSS/content outside <head>/<body>.
            # Detect and wrap into a valid HTML skeleton if needed.
            html = _repair_html_structure(html)

            # Validate
            issues = _validate_game_html(html, master)
            if issues and attempt < max_attempts - 1:
                logger.warning(
                    "Game validation issues (attempt %d): %s",
                    attempt + 1,
                    "; ".join(issues),
                )
                prompt += (
                    "\n\nPREVIOUS ATTEMPT HAD ISSUES: "
                    + "; ".join(issues)
                    + "\nFix these issues. Output ONLY the complete HTML."
                )
                continue

            if issues:
                logger.warning(
                    "Game has issues but using anyway: %s",
                    "; ".join(issues),
                )
                logger.warning(
                    "Note: Interactive games work best with code-capable models "
                    "(Claude Sonnet/Opus, GPT-4o). Smaller models may produce "
                    "incomplete HTML. Try: clawed config set-model ollama -m "
                    "deepseek-coder-v2:cloud"
                )

            # Save
            fname = f"game_{safe_filename(master.title)}.html"
            game_path = output_dir / fname
            game_path.write_text(html, encoding="utf-8")

            logger.info(
                "Game compiled: %s (%d bytes)",
                game_path.name,
                len(html),
            )
            return game_path

        except Exception as e:
            logger.error("Game generation failed (attempt %d): %s", attempt + 1, e)
            if attempt == max_attempts - 1:
                raise

    # Should never reach here
    raise RuntimeError("Game generation failed after all attempts")
