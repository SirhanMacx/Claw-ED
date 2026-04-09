"""Tool: generate_animation — create animated educational videos using Manim.

Produces 3Blue1Brown-style educational animations for:
- Historical timelines with event markers and date labels
- Cause-effect diagrams with connecting arrows
- Process flows with sequential reveals
- Concept maps with branching relationships
- Venn comparisons for comparing topics
- Vocabulary cards with flip animations

Adapted from the Hermes agent manim-video skill with education-specific
templates and cognitive load limits (max 6 elements, 2-3s pauses).
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.failure_codes import FailureCode  # noqa: F401 — used in error messages

logger = logging.getLogger(__name__)

# Safe output directory for rendered animations
def _get_animation_dir() -> Path:
    from clawed.paths import data_dir
    return data_dir() / "animations"

_ANIMATION_DIR = _get_animation_dir()

# Maximum subprocess timeout for Manim render
_RENDER_TIMEOUT = 120


class GenerateAnimationTool:
    """Create animated educational videos using Manim Community Edition."""

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_animation",
                "description": (
                    "Create an animated educational video (timeline, diagram, "
                    "process flow, concept map, comparison, vocabulary cards) "
                    "using Manim. Renders to MP4 video. Use this when the teacher "
                    "asks for an animation, animated explanation, visual timeline, "
                    "or motion graphic for their lesson."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": (
                                "What to animate — e.g., "
                                "'Timeline of the American Revolution 1775-1783'"
                            ),
                        },
                        "animation_type": {
                            "type": "string",
                            "description": "Type of animation to create",
                            "enum": [
                                "timeline",
                                "diagram",
                                "process",
                                "concept",
                                "comparison",
                                "vocabulary",
                            ],
                        },
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Content points to visualize. For timelines: "
                                "'1775: Lexington and Concord'. For diagrams: "
                                "'cause → effect' pairs. For concepts: branch labels."
                            ),
                        },
                        "style": {
                            "type": "string",
                            "description": "Visual style for the animation",
                            "enum": ["educational", "dramatic", "minimal"],
                            "default": "educational",
                        },
                        "quality": {
                            "type": "string",
                            "description": "Render quality: low (480p, fast) or medium (720p)",
                            "enum": ["low", "medium"],
                            "default": "low",
                        },
                    },
                    "required": ["topic", "animation_type", "key_points"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        topic = params["topic"]
        animation_type = params["animation_type"]
        key_points = params.get("key_points", [])
        style = params.get("style", "educational")
        quality = params.get("quality", "low")

        # Check Manim availability
        try:
            import manim  # noqa: F401
        except ImportError:
            return ToolResult(
                text=(
                    "Animation requires Manim Community Edition. "
                    "Install with: pip install 'manim>=0.18' pyav\n\n"
                    "On macOS you may also need: brew install cairo pango ffmpeg\n"
                    "On Ubuntu: apt install libcairo2-dev libpango1.0-dev ffmpeg"
                ),
                data={"failure_code": FailureCode.MISSING_DEPENDENCY.value},
            )

        if not key_points:
            return ToolResult(
                text="Please provide key_points — the content to visualize in the animation.",
            )

        # Report progress
        if context.progress_callback:
            await context.notify_progress(f"Creating {animation_type} animation for: {topic}")

        # Stage 1: Generate Manim scene code
        scene_code = self._build_scene(topic, animation_type, key_points, style)
        if not scene_code:
            return ToolResult(
                text=f"Unsupported animation type: {animation_type}. "
                f"Supported: timeline, diagram, process, concept, comparison, vocabulary",
            )

        # Stage 2: Write scene to temp file
        _ANIMATION_DIR.mkdir(parents=True, exist_ok=True)
        scene_hash = hashlib.md5(scene_code.encode()).hexdigest()[:8]
        scene_file = _ANIMATION_DIR / f"scene_{scene_hash}.py"
        scene_file.write_text(scene_code, encoding="utf-8")

        # Determine class name from the template
        class_name = self._extract_class_name(scene_code)

        # Stage 3: Render with Manim
        quality_flag = "-ql" if quality == "low" else "-qm"
        cmd = [
            "manim", "render",
            quality_flag,
            str(scene_file),
            class_name,
            "--media_dir", str(_ANIMATION_DIR / "media"),
        ]

        if context.progress_callback:
            await context.notify_progress("Rendering animation (this may take a moment)...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_RENDER_TIMEOUT,
                cwd=str(_ANIMATION_DIR),
            )

            if result.returncode != 0:
                logger.warning("Manim render failed: %s", result.stderr[:500])

                # Stage 3b: Retry with simplified scene
                if context.progress_callback:
                    await context.notify_progress("Simplifying and retrying render...")

                scene_code = self._simplify_scene(scene_code)
                scene_file.write_text(scene_code, encoding="utf-8")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=_RENDER_TIMEOUT,
                    cwd=str(_ANIMATION_DIR),
                )

                if result.returncode != 0:
                    return ToolResult(
                        text=(
                            f"Animation render failed. Manim error:\n"
                            f"{result.stderr[:300]}\n\n"
                            f"Try simplifying the key_points or using fewer items."
                        ),
                    )

        except subprocess.TimeoutExpired:
            return ToolResult(
                text="Animation render timed out (>120s). Try fewer key_points or 'low' quality.",
            )
        except FileNotFoundError:
            return ToolResult(
                text=(
                    "Could not find 'manim' command. Make sure Manim is installed and on your PATH.\n"
                    "Install with: pip install 'manim>=0.18' pyav"
                ),
                data={"failure_code": FailureCode.MISSING_DEPENDENCY.value},
            )

        # Stage 4: Find the output video
        video_path = self._find_output_video(class_name, quality)
        if not video_path:
            return ToolResult(
                text="Render completed but output video not found. Check Manim installation.",
            )

        # Stage 5: Deliver
        file_size_kb = video_path.stat().st_size // 1024
        logger.info("Animation rendered: %s (%d KB)", video_path.name, file_size_kb)

        return ToolResult(
            text=(
                f"Created {animation_type} animation: **{topic}**\n"
                f"Video: {video_path.name} ({file_size_kb} KB)\n"
                f"Points visualized: {len(key_points)}"
            ),
            files=[video_path],
            side_effects=[f"Rendered {animation_type} animation: {video_path.name}"],
        )

    def _build_scene(
        self,
        topic: str,
        animation_type: str,
        key_points: list[str],
        style: str,
    ) -> str | None:
        """Build Manim scene code from template + data."""
        from clawed.animation_templates import COLORS, get_template

        template = get_template(animation_type)
        if not template:
            return None

        # Color scheme based on style
        if style == "dramatic":
            colors = {**COLORS, "bg": "#0a0a1a", "accent": "#ff2e63"}
        elif style == "minimal":
            colors = {**COLORS, "bg": "#ffffff", "text": "#333333", "accent": "#2196f3"}
        else:
            colors = COLORS

        # Parse key_points into template-specific data structures
        if animation_type == "timeline":
            events = self._parse_timeline_events(key_points)
            return template.format(
                title=topic[:60],
                events_repr=repr(events),
                text_color=colors["text"],
                accent_color=colors["accent"],
            )

        elif animation_type == "diagram":
            causes, effects = self._parse_cause_effect(key_points)
            return template.format(
                title=topic[:60],
                causes_repr=repr(causes),
                effects_repr=repr(effects),
                text_color=colors["text"],
                accent_color=colors["accent"],
                success_color=colors["success"],
            )

        elif animation_type == "process":
            return template.format(
                title=topic[:60],
                steps_repr=repr(key_points[:6]),
                text_color=colors["text"],
                accent_color=colors["accent"],
                info_color=colors["info"],
            )

        elif animation_type == "concept":
            return template.format(
                center=topic[:30],
                branches_repr=repr(key_points[:6]),
                text_color=colors["text"],
                accent_color=colors["accent"],
                info_color=colors["info"],
            )

        elif animation_type == "comparison":
            left, shared, right, left_label, right_label = self._parse_comparison(key_points, topic)
            return template.format(
                title=topic[:60],
                left_label=left_label,
                right_label=right_label,
                left_items_repr=repr(left),
                shared_items_repr=repr(shared),
                right_items_repr=repr(right),
                text_color=colors["text"],
                accent_color=colors["accent"],
                info_color=colors["info"],
                success_color=colors["success"],
            )

        elif animation_type == "vocabulary":
            vocab = self._parse_vocabulary(key_points)
            return template.format(
                title=topic[:60],
                vocab_repr=repr(vocab),
                text_color=colors["text"],
                accent_color=colors["accent"],
                info_color=colors["info"],
            )

        return None

    # ── Data parsers ─────────────────────────────────────────────────

    @staticmethod
    def _parse_timeline_events(points: list[str]) -> list[tuple[int, str]]:
        """Parse 'YEAR: description' or 'YEAR description' into (year, label) tuples."""
        import re
        events = []
        for p in points:
            m = re.match(r'(\d{3,4})\s*[:.\-–—]\s*(.+)', p.strip())
            if m:
                events.append((int(m.group(1)), m.group(2).strip()))
            else:
                # Try to find a year anywhere in the string
                ym = re.search(r'(\d{4})', p)
                if ym:
                    label = re.sub(r'\d{4}', '', p).strip(' :.-–—')
                    events.append((int(ym.group(1)), label or p))
        return events

    @staticmethod
    def _parse_cause_effect(points: list[str]) -> tuple[list[str], list[str]]:
        """Parse 'cause → effect' pairs from key_points."""
        causes, effects = [], []
        for p in points:
            # Split on arrow-like separators
            for sep in ['→', '->', '=>', '➜', '⟹', ' leads to ', ' causes ', ' results in ']:
                if sep in p:
                    parts = p.split(sep, 1)
                    causes.append(parts[0].strip())
                    effects.append(parts[1].strip())
                    break
            else:
                # No separator — treat as cause, generate generic effect
                causes.append(p.strip())
                effects.append("(effect)")
        return causes, effects

    @staticmethod
    def _parse_comparison(points: list[str], topic: str) -> tuple[list[str], list[str], list[str], str, str]:
        """Parse comparison points into left-only, shared, right-only."""
        left, shared, right = [], [], []
        left_label, right_label = "A", "B"

        # Try to extract labels from topic (e.g., "Federalists vs Anti-Federalists")
        for sep in [' vs ', ' vs. ', ' versus ', ' compared to ', ' and ']:
            if sep in topic.lower():
                idx = topic.lower().index(sep)
                left_label = topic[:idx].strip()
                right_label = topic[idx + len(sep):].strip()
                break

        for p in points:
            p_lower = p.lower().strip()
            if p_lower.startswith("both:") or p_lower.startswith("shared:"):
                shared.append(p.split(":", 1)[1].strip())
            elif p_lower.startswith("left:") or p_lower.startswith(f"{left_label.lower()}:"):
                left.append(p.split(":", 1)[1].strip())
            elif p_lower.startswith("right:") or p_lower.startswith(f"{right_label.lower()}:"):
                right.append(p.split(":", 1)[1].strip())
            else:
                # Auto-distribute
                if len(left) <= len(right):
                    left.append(p.strip())
                else:
                    right.append(p.strip())

        return left, shared, right, left_label[:20], right_label[:20]

    @staticmethod
    def _parse_vocabulary(points: list[str]) -> list[tuple[str, str]]:
        """Parse 'term: definition' pairs."""
        vocab = []
        for p in points:
            for sep in [':', ' - ', ' — ', ' – ']:
                if sep in p:
                    parts = p.split(sep, 1)
                    vocab.append((parts[0].strip(), parts[1].strip()))
                    break
            else:
                vocab.append((p.strip(), "(definition)"))
        return vocab

    # ── Utility methods ──────────────────────────────────────────────

    @staticmethod
    def _extract_class_name(code: str) -> str:
        """Extract the Scene class name from Manim code."""
        import re
        m = re.search(r'class\s+(\w+)\s*\(', code)
        return m.group(1) if m else "Scene"

    @staticmethod
    def _simplify_scene(code: str) -> str:
        """Simplify a scene for retry — reduce animations, shorten waits."""
        code = code.replace("run_time=1.5", "run_time=0.5")
        code = code.replace("run_time=1", "run_time=0.5")
        code = code.replace("run_time=0.8", "run_time=0.3")
        code = code.replace("self.wait(2)", "self.wait(0.5)")
        code = code.replace("self.wait(1.5)", "self.wait(0.3)")
        return code

    def _find_output_video(self, class_name: str, quality: str) -> Path | None:
        """Find the rendered video file in Manim's media output."""
        media_dir = _ANIMATION_DIR / "media" / "videos"
        if not media_dir.exists():
            return None

        # Manim outputs to media/videos/{scene_file}/{quality}/{ClassName}.mp4
        quality_dir = "480p15" if quality == "low" else "720p30"

        # Search all scene directories for our class
        for scene_dir in media_dir.iterdir():
            if not scene_dir.is_dir():
                continue
            target = scene_dir / quality_dir / f"{class_name}.mp4"
            if target.exists() and target.stat().st_size > 0:
                return target

        # Fallback: find any recently created MP4
        import time
        now = time.time()
        for mp4 in media_dir.rglob("*.mp4"):
            if now - mp4.stat().st_mtime < 300:  # created in last 5 min
                return mp4

        return None
