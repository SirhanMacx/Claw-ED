"""Small handlers for demo, persona, settings, progress, model switch."""
from __future__ import annotations

import logging

from clawed.gateway_response import GatewayResponse

logger = logging.getLogger(__name__)

class DemoHandler:
    async def run(self, teacher_id: str) -> GatewayResponse:
        try:
            from clawed.generation import generate_lesson
            from clawed.router import parse_intent
            from clawed.state import TeacherSession

            parsed = parse_intent("generate a sample lesson on photosynthesis for 6th grade science")
            session = TeacherSession.load(teacher_id)
            text = await generate_lesson(parsed, session)
            return GatewayResponse(text=text)
        except Exception as e:
            return GatewayResponse(text=f"Demo failed: {e}")

class PersonaHandler:
    async def show(self, teacher_id: str) -> GatewayResponse:
        try:
            from clawed.state import TeacherSession
            session = TeacherSession.load(teacher_id)
            if not session.persona:
                return GatewayResponse(
                    text="No teaching persona yet. Upload some lesson files and I'll learn your style!"
                )
            p = session.persona
            lines = [
                "Your teaching persona:",
                f"  Style: {p.teaching_style}",
                f"  Tone: {p.tone}",
                f"  Subject: {p.subject_area}",
            ]
            if p.favorite_strategies:
                lines.append(f"  Strategies: {', '.join(p.favorite_strategies[:3])}")
            return GatewayResponse(text="\n".join(lines))
        except Exception as e:
            return GatewayResponse(text=f"Could not load persona: {e}")

class SettingsHandler:
    async def show(self, teacher_id: str) -> GatewayResponse:
        try:
            from clawed.models import AppConfig
            config = AppConfig.load()
            lines = [
                "Your settings:",
                f"  Provider: {config.provider}",
                f"  Model: {config.ollama_model}",
                f"  Output: {config.output_dir}",
                f"  Export format: {config.export_format}",
            ]
            if config.teacher_profile:
                tp = config.teacher_profile
                lines.append(f"  Name: {tp.name}")
                lines.append(f"  Subjects: {', '.join(tp.subjects)}")
                lines.append(f"  Grades: {', '.join(tp.grade_levels)}")
            return GatewayResponse(text="\n".join(lines))
        except Exception as e:
            return GatewayResponse(text=f"Could not load settings: {e}")

class ProgressHandler:
    async def show(self, teacher_id: str) -> GatewayResponse:
        try:
            from clawed.analytics import get_teacher_stats
            stats = get_teacher_stats(teacher_id)
            lines = [
                "Your progress:",
                f"  Lessons generated: {stats.get('total_lessons', 0)}",
                f"  Units planned: {stats.get('total_units', 0)}",
                f"  Lessons rated: {stats.get('rated_lessons', 0)}",
                f"  Average rating: {stats.get('overall_avg_rating', 0):.1f}/5",
            ]
            return GatewayResponse(text="\n".join(lines))
        except ImportError:
            return GatewayResponse(text="No progress data yet. Generate some lessons first!")

class ModelSwitchHandler:
    async def switch(self, teacher_id: str, text: str) -> GatewayResponse:
        try:
            from clawed.models import AppConfig, LLMProvider
            config = AppConfig.load()
            lower = text.lower()
            if "ollama" in lower:
                config.provider = LLMProvider.OLLAMA
            elif "anthropic" in lower:
                config.provider = LLMProvider.ANTHROPIC
            elif "openai" in lower:
                config.provider = LLMProvider.OPENAI
            else:
                return GatewayResponse(text="Supported providers: ollama, anthropic, openai")
            config.save()
            return GatewayResponse(text=f"Switched to {config.provider.value}.")
        except Exception as e:
            return GatewayResponse(text=f"Could not switch model: {e}")
