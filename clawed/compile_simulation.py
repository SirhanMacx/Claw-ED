"""Compile interactive HTML simulations from lesson content.

Every simulation is unique — the LLM designs the visualization, controls,
and scientific behavior based on the lesson content. No templates.

The compiler:
1. Extracts simulation-worthy content from MasterContent
2. Asks the LLM to design and code a complete single-file HTML simulation
3. Validates the output (loads, contains educational content, has controls)
4. Falls back to regeneration if the simulation is broken

Usage:
    from clawed.compile_simulation import compile_simulation
    path = await compile_simulation(master, persona, output_dir)
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

SIMULATION_SYSTEM_PROMPT = """\
You are an expert educational simulation developer. You create single-file \
HTML interactive simulations that let students explore scientific concepts \
through direct manipulation. Every simulation you make is UNIQUE — different \
visualization, different controls, different interaction pattern.

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
- The simulation MUST work on phones, tablets, Chromebooks (responsive, touch).
- Add a small footer: "Made with Claw-ED — github.com/SirhanMacx/Claw-ED"

WHAT A SIMULATION IS — AND IS NOT:
- NO scoring, NO levels, NO competition, NO start/end screens, NO win/lose.
- YES interactive controls: sliders, range inputs, buttons, drag handles.
- YES real-time visualization: Canvas, Three.js, SVG animations.
- YES science-accurate behavior: use REAL formulas for physics, REAL reactions \
for chemistry, REAL population models for biology.
- YES educational annotations: labels showing current values, formulas \
displayed on screen, brief explanations of what's happening.
- YES parameter adjustment: let students change gravity, mass, speed, \
concentration, temperature, frequency, wavelength, etc.
- YES a reset button to return everything to initial state.

EXAMPLES OF GREAT SIMULATIONS:
- Pendulum with adjustable gravity, length, and mass — shows period formula.
- Wave interference: two sources, adjustable frequency and phase.
- Chemical equilibrium: adjust temperature/pressure, see Le Chatelier's principle.
- Projectile motion: adjust angle, velocity, gravity — shows trajectory equation.
- Population dynamics: prey/predator with adjustable birth/death rates.
- Circuit simulator: drag resistors and batteries, see current flow.
- Orbital mechanics: adjust mass and velocity, watch orbit change.
- Gas laws: adjust P, V, T with a piston visualization.

VISUALS — DO NOT USE IMAGE FILES. Create ALL visuals programmatically:
- Use Three.js for immersive 3D scenes themed to the concept. \
  Molecular dynamics = 3D molecules. Orbital mechanics = 3D solar system. \
  Fluid dynamics = 3D particle systems.
- Use CSS gradients, animations, box-shadows, and transforms for 2D polish.
- Use HTML Canvas for physics visualizations, graphs, trajectories.
- Use CSS shapes and emoji for icons — never <img> tags.
- Use SVG inline for any detailed graphics (diagrams, symbols, vectors).
- The simulation should feel IMMERSIVE — like the student is inside a lab, \
  not reading a textbook. Real-time updates, smooth animations, responsive controls.
- Go ABOVE AND BEYOND visually. This should look like a real scientific tool.

INTERACTIVE CONTROLS:
- Use <input type="range"> sliders with visible labels and current values.
- Include a prominent RESET button to restore initial parameters.
- Show real-time readouts: current velocity, force, energy, concentration, etc.
- Display the relevant formula(s) on screen so students connect math to visuals.
- Controls should be intuitive — a student should understand what each does.
- Consider drag-and-drop for repositioning objects in the simulation.

WHAT MAKES A GREAT SIMULATION:
- The visualization accurately reflects the underlying science.
- Students can form hypotheses ("what if I increase mass?") and test them.
- Real-time feedback — changes are visible immediately as parameters adjust.
- Educational labels explain WHY things happen, not just WHAT happens.
- Multiple parameters interact realistically (e.g., changing mass affects \
  both momentum and gravitational force).
"""


def _extract_simulation_content(master: MasterContent) -> str:
    """Extract educational content from MasterContent for simulation generation.

    Accepts MasterContent or DailyLesson (single-agent path lacks subject/grade_level).
    """
    parts = [
        f"LESSON: {master.title}",
        f"SUBJECT: {getattr(master, 'subject', 'Science')}",
        f"GRADE: {getattr(master, 'grade_level', '')}",
        f"TOPIC: {getattr(master, 'topic', master.title)}",
        f"OBJECTIVE: {master.objective}",
    ]

    if master.vocabulary:
        parts.append("\nKEY VOCABULARY:")
        for v in master.vocabulary:
            parts.append(
                f"  - {v.term}: {v.definition}"
                + (f" (context: {v.context_sentence})" if v.context_sentence else "")
            )

    direct_instruction = getattr(master, "direct_instruction", None)
    if direct_instruction and not isinstance(direct_instruction, str):
        parts.append("\nKEY CONCEPTS:")
        for section in direct_instruction:
            parts.append(f"  - {getattr(section, 'heading', str(section))}")
            if hasattr(section, "key_points") and section.key_points:
                for pt in section.key_points[:3]:
                    parts.append(f"    * {pt}")
    elif isinstance(direct_instruction, str) and direct_instruction:
        parts.append(f"\nKEY CONCEPTS:\n{direct_instruction[:500]}")

    guided_notes = getattr(master, "guided_notes", None)
    if guided_notes:
        parts.append("\nKEY FACTS:")
        for note in guided_notes:
            parts.append(f"  - {note.prompt} -> {note.answer}")

    exit_ticket = getattr(master, "exit_ticket", None)
    if exit_ticket:
        parts.append("\nCONCEPT QUESTIONS:")
        for i, q in enumerate(exit_ticket if isinstance(exit_ticket, list) else [], 1):
            question_text = getattr(q, "question", str(q))
            parts.append(f"  {i}. {question_text}")

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
        title_text = title_match.group(1).strip() if title_match else "Interactive Simulation"
        return (
            f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
            f"<meta charset=\"UTF-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"<title>{title_text}</title>\n"
            f"<style>\n{html}\n</style>\n</head>\n<body></body>\n</html>"
        )

    _preamble = html[:html_tag_end + 1]  # everything up to and including <html ...>
    rest = html[html_tag_end + 1:].strip()

    # Extract bare title text (first non-tag, non-CSS line after <html>)
    # This catches lines like "Pendulum Simulation" emitted before the CSS
    title_text = "Interactive Simulation"
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


def _validate_simulation_html(html: str, master: MasterContent) -> list[str]:
    """Validate that the generated HTML is a working simulation."""
    issues = []

    if not html or len(html) < 500:
        issues.append("HTML is too short to be a real simulation")

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
            f"Topic words ({', '.join(topic_words)}) not found in simulation"
        )

    if master.vocabulary:
        first_term = master.vocabulary[0].term.lower()
        if first_term not in html_lower:
            issues.append(
                f"First vocabulary term '{first_term}' not in simulation"
            )

    # Check for interactive controls (sliders, range inputs, buttons)
    has_controls = any(
        pattern in html_lower
        for pattern in [
            'type="range"',
            "type='range'",
            "<button",
            "<select",
            'type="number"',
            "type='number'",
            "slider",
            "addeventlistener",
            "oninput",
            "onclick",
        ]
    )
    if not has_controls:
        issues.append("No interactive controls found (sliders, buttons, inputs)")

    return issues


async def compile_simulation(
    master: MasterContent | Any,
    persona: TeacherPersona | None = None,
    output_dir: Path | None = None,
    config: AppConfig | None = None,
    simulation_type: str = "",
) -> Path:
    """Generate a unique interactive HTML simulation from lesson content.

    The LLM designs the visualization, controls, and scientific behavior
    from scratch every time. No templates.

    Args:
        master: The lesson's MasterContent (source of truth).
        persona: Teacher persona for voice/style matching.
        output_dir: Where to save the .html file.
        config: App config for model routing.
        simulation_type: Specific simulation type request ("physics",
            "chemistry", "math", "biology"). If empty, LLM decides.

    Returns:
        Path to the generated .html simulation file.
    """
    if output_dir is None:
        from clawed.io import output_dir as get_output_dir
        output_dir = get_output_dir()
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = config or AppConfig.load()
    # Route to DEEP tier within the teacher's chosen provider.
    config = route_model("simulation_generate", config)

    # Simulation generation requires code-capable models. Warn if using a model
    # that is known to produce broken HTML (small local Ollama models).
    code_weak_models = {"qwen3.5:cloud", "llama3.2:latest", "phi3:latest"}
    resolved_model = getattr(config, "ollama_model", "") or ""
    if resolved_model in code_weak_models:
        logger.warning(
            "Simulation generation works best with code-capable models. "
            "Model '%s' may produce broken HTML. Consider using a larger "
            "model (minimax, deepseek-coder, codestral) or a cloud provider "
            "(Anthropic, OpenAI) for simulations.",
            resolved_model,
        )

    client = LLMClient(config)

    # Build the simulation generation prompt
    content = _extract_simulation_content(master)

    prompt_parts = [
        "Design and code a COMPLETE, UNIQUE, single-file HTML interactive "
        "simulation for this lesson.\n",
        content,
    ]

    if simulation_type:
        prompt_parts.append(
            f"\nSIMULATION TYPE: {simulation_type}\n"
            "Focus on this domain. Use real formulas and accurate scientific "
            "behavior for this field."
        )
    else:
        prompt_parts.append(
            "\nNo specific type requested — analyze the lesson content and "
            "pick the most appropriate simulation. A physics lesson should "
            "have motion/forces visualization. A chemistry lesson should "
            "have molecular/reaction visualization. Think about what "
            "interactive model actually helps students UNDERSTAND this concept."
        )

    if persona:
        prompt_parts.append(
            f"\nTEACHER'S STYLE: {persona.tone or 'engaging'}\n"
            f"Grade level: {getattr(master, 'grade_level', '')}\n"
            "Match the complexity and language to this teacher and grade."
        )

    prompt = "\n".join(prompt_parts)

    # Generate with retry
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            html = await client.generate(
                prompt=prompt,
                system=SIMULATION_SYSTEM_PROMPT,
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
            issues = _validate_simulation_html(html, master)
            if issues and attempt < max_attempts - 1:
                logger.warning(
                    "Simulation validation issues (attempt %d): %s",
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
                    "Simulation has issues but using anyway: %s",
                    "; ".join(issues),
                )
                logger.warning(
                    "Note: Interactive simulations work best with code-capable "
                    "models (Claude Sonnet/Opus, GPT-4o). Smaller models may "
                    "produce incomplete HTML. Try: clawed config set-model "
                    "ollama -m deepseek-coder-v2:cloud"
                )

            # Save
            topic = getattr(master, "topic", master.title)
            fname = f"{safe_filename(topic)}_simulation.html"
            sim_path = output_dir / fname
            sim_path.write_text(html, encoding="utf-8")

            logger.info(
                "Simulation compiled: %s (%d bytes)",
                sim_path.name,
                len(html),
            )
            return sim_path

        except Exception as e:
            logger.error("Simulation generation failed (attempt %d): %s", attempt + 1, e)
            if attempt == max_attempts - 1:
                raise

    # Should never reach here
    raise RuntimeError("Simulation generation failed after all attempts")
