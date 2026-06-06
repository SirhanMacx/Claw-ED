"""Tool: generate_video — turn a topic into a narrated educational video.

A faceless, local-first video pipeline: the LLM drafts a short script
(title + key points + per-point narration) from the teacher's topic, those
become slides, slides are rendered to PNG via Chrome headless, narrated with
a free neural voice (edge-tts, macOS ``say`` fallback), animated with a
Ken-Burns zoom, captioned, and assembled into an MP4.

Mirrors ``generate_animation.py``: declares ``risk_level``, dep-checks before
doing work, shells out to a renderer (``clawed.compile_video``), writes the
MP4 into the data dir, and returns a :class:`ToolResult`. Free and offline —
no paid API, no cloud, no telemetry. edge-tts uses Microsoft's free neural
voices (network, no key); when unavailable the build degrades gracefully.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.failure_codes import FailureCode

logger = logging.getLogger(__name__)


def _video_dir():
    from clawed.paths import data_dir
    return data_dir() / "videos"


_SCRIPT_SYSTEM_PROMPT = """\
You are an expert educational scriptwriter for short, faceless explainer \
videos (think 60-second study reels). You distill a topic into a tight, \
accurate, classroom-appropriate micro-script.

Return ONLY valid JSON — no markdown fencing, no commentary — in exactly \
this shape:

{
  "title": "<a punchy 2-5 word video title>",
  "points": [
    "<key point 1: a short concept, optionally 'Term: short explanation'>",
    "<key point 2>",
    "... 4 to 6 points total ..."
  ],
  "narration": [
    "<1-2 spoken sentences narrating point 1 — natural, conversational>",
    "<1-2 spoken sentences narrating point 2>",
    "... one narration line per point, same order ..."
  ]
}

RULES:
- 4 to 6 points. "points" and "narration" MUST be the same length.
- Points are concise on-screen text (a few words). Narration is what the \
voice says — full, natural sentences a teacher would speak aloud.
- Be factually accurate and age-appropriate for the given grade level.
- No emojis. No special characters that would look odd as a caption.
- Keep each narration line short enough to speak in ~6-10 seconds.
"""


class GenerateVideoTool:
    """Create a narrated educational video (slides + neural voiceover + motion)."""

    # Writes a rendered MP4 to disk and shells out to ffmpeg/Chrome, so it
    # goes through the approval gate exactly like generate_animation.
    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "generate_video",
                "description": (
                    "Create a narrated educational video from a topic — slides "
                    "with a free neural voiceover, Ken-Burns motion, and burned-in "
                    "captions, assembled into an MP4. Use this when the teacher asks "
                    "for a video, explainer, narrated lesson, study reel, or "
                    "video summary of a topic. Runs locally and free (no paid API). "
                    "Different from generate_animation, which makes silent vector "
                    "(Manim) diagrams; this produces a spoken, captioned video."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": (
                                "What the video is about — e.g. "
                                "'The causes of the Cold War' or 'Photosynthesis'."
                            ),
                        },
                        "grade_level": {
                            "type": "string",
                            "description": "Target grade level (e.g. '9', 'AP', 'middle school').",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Subject area (e.g. 'Global History', 'Biology').",
                        },
                        "num_scenes": {
                            "type": "integer",
                            "description": (
                                "Approximate number of teaching scenes (key points). "
                                "The final video adds an intro and outro around these."
                            ),
                            "default": 6,
                        },
                        "aspect": {
                            "type": "string",
                            "description": "Aspect ratio of the video.",
                            "enum": ["9:16", "16:9", "1:1", "4:5"],
                            "default": "9:16",
                        },
                        "voice": {
                            "type": "string",
                            "description": (
                                "edge-tts neural voice id. Defaults to a clear "
                                "US-English narrator."
                            ),
                            "default": "en-US-AndrewMultilingualNeural",
                        },
                    },
                    "required": ["topic"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        topic = (params.get("topic") or "").strip()
        if not topic:
            return ToolResult(text="ERROR: topic is required to make a video.")

        grade_level = (params.get("grade_level") or "").strip()
        subject = (params.get("subject") or "").strip()
        try:
            num_scenes = int(params.get("num_scenes", 6))
        except (TypeError, ValueError):
            num_scenes = 6
        num_scenes = max(3, min(8, num_scenes))
        aspect = params.get("aspect", "9:16") or "9:16"
        voice = params.get("voice", "en-US-AndrewMultilingualNeural") or "en-US-AndrewMultilingualNeural"

        # ── Dependency check (friendly, never crash) ──────────────────
        from clawed.compile_video import check_dependencies

        deps = check_dependencies()
        hard_missing = [name for name in ("ffmpeg", "ffprobe", "chrome") if not deps.get(name)]
        tts_missing = not deps.get("edge-tts") and not deps.get("say")

        if hard_missing or tts_missing:
            lines = ["I can't build the video yet — some free tools are missing:"]
            if "ffmpeg" in hard_missing or "ffprobe" in hard_missing:
                lines.append("  - ffmpeg/ffprobe: install with `brew install ffmpeg` (macOS) "
                             "or `sudo apt install ffmpeg` (Linux).")
            if "chrome" in hard_missing:
                lines.append("  - Google Chrome (used to render slides): install Chrome, "
                             "or set the EDUAGENT_CHROME env var to its path.")
            if tts_missing:
                lines.append("  - A neural voice: install the free one with `pip install edge-tts` "
                             "(on macOS the built-in `say` voice works too).")
            lines.append("Once those are in place, ask me again and I'll render the video.")
            return ToolResult(
                text="\n".join(lines),
                data={"failure_code": FailureCode.MISSING_DEPENDENCY.value},
            )

        # ── Stage 1: draft the script with the LLM ────────────────────
        context.notify_progress(f"Writing a script for: {topic}")
        try:
            title, points, narration = await self._draft_script(
                topic, grade_level, subject, num_scenes, context,
            )
        except Exception as exc:
            logger.error("Video script drafting failed: %s", exc)
            return ToolResult(
                text=f"I couldn't draft the video script ({exc}). "
                     f"Try rephrasing the topic or try again."
            )

        if not points:
            return ToolResult(
                text="I couldn't turn that topic into teaching points. "
                     "Try a more specific topic."
            )

        # ── Stage 2: map to scenes ────────────────────────────────────
        from clawed.compile_video import build_video, scenes_from_lesson

        scenes = scenes_from_lesson(title or topic, points, narration, aspect=aspect)
        meta: dict[str, Any] = {
            "aspect": aspect,
            "voice": voice,
            "brand": "Claw-ED",
            "tag": (subject.upper()[:18] if subject else "EDUCATIONAL"),
        }

        # ── Stage 3: render the video ─────────────────────────────────
        out_dir = _video_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        from clawed.io import safe_filename
        out_path = out_dir / f"{safe_filename(title or topic)}.mp4"

        context.notify_progress(
            f"Rendering {len(scenes)} scenes with narration (this can take a minute)…"
        )
        try:
            video_path = build_video(scenes, meta, out_path)
        except Exception as exc:
            # compile_video raises VideoDependencyError / VideoBuildError;
            # surface either as a friendly, honest failure.
            from clawed.compile_video import VideoDependencyError

            logger.error("Video render failed: %s", exc)
            if isinstance(exc, VideoDependencyError):
                return ToolResult(
                    text=f"The video couldn't be built — {exc}",
                    data={"failure_code": FailureCode.MISSING_DEPENDENCY.value},
                )
            return ToolResult(
                text=f"The video render failed partway through: {exc}. "
                     f"No video was produced. Try fewer scenes or a simpler topic."
            )

        # ── Deliver ───────────────────────────────────────────────────
        size_kb = video_path.stat().st_size // 1024
        engine = "neural voice (edge-tts)" if deps.get("edge-tts") else "system voice (say)"
        return ToolResult(
            text=(
                f"Here's your narrated video on **{title or topic}** "
                f"({len(scenes)} scenes, {aspect}, {size_kb} KB).\n"
                f"Voiceover: {engine}. Saved to: {video_path}\n"
                f"Drop it straight into a slideshow, your LMS, or a class warm-up."
            ),
            files=[video_path],
            side_effects=[f"Rendered narrated video: {video_path.name}"],
        )

    # ── Helpers ───────────────────────────────────────────────────────

    async def _draft_script(
        self,
        topic: str,
        grade_level: str,
        subject: str,
        num_scenes: int,
        context: AgentContext,
    ) -> tuple[str, list[str], list[str]]:
        """Ask the LLM for a title + key points + per-point narration.

        Uses the same model-access pattern as the other compilers
        (LLMClient + model_router). Returns (title, points, narration)
        with points/narration aligned to the same length.
        """
        from clawed.llm import LLMClient
        from clawed.model_router import route as route_model

        config = getattr(context, "config", None)
        if config is None:
            from clawed.models import AppConfig
            config = AppConfig.load()
        config = route_model("lesson_plan", config)  # DEEP tier — accuracy matters
        client = LLMClient(config)

        audience = []
        if grade_level:
            audience.append(f"grade level: {grade_level}")
        if subject:
            audience.append(f"subject: {subject}")
        audience_str = (" (" + ", ".join(audience) + ")") if audience else ""

        prompt = (
            f"Write a short faceless educational video script about:\n"
            f"{topic}{audience_str}\n\n"
            f"Use about {num_scenes} key points. Return ONLY the JSON described."
        )

        raw = await client.generate(
            prompt=prompt,
            system=_SCRIPT_SYSTEM_PROMPT,
            temperature=0.6,
            max_tokens=1600,
            demo_hint="video_script",
        )

        title, points, narration = self._parse_script_json(raw, topic, num_scenes)

        # Fallback when the model returns nothing usable: build points from
        # the topic itself so the teacher still gets a video.
        if not points:
            title = title or topic
            points = [topic]
            narration = [f"Let's take a quick look at {topic}."]

        # Align lengths.
        if len(narration) < len(points):
            narration += [points[i] for i in range(len(narration), len(points))]
        elif len(narration) > len(points):
            narration = narration[: len(points)]

        return title or topic, points, narration

    @staticmethod
    def _parse_script_json(
        raw: str, topic: str, num_scenes: int
    ) -> tuple[str, list[str], list[str]]:
        """Best-effort parse of the model's JSON script output."""
        text = (raw or "").strip()
        # Strip markdown fencing if present.
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()

        data: Any = None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Grab the first {...} block.
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    data = None

        if not isinstance(data, dict):
            return topic, [], []

        title = str(data.get("title") or topic).strip()
        points = [str(p).strip() for p in (data.get("points") or []) if str(p).strip()]
        narration = [str(n).strip() for n in (data.get("narration") or []) if str(n).strip()]
        # Trim to a sane maximum.
        points = points[: max(3, min(8, num_scenes + 1))]
        return title, points, narration
