"""The brain of Claw-ED — transport-agnostic message gateway.

Every message from every transport goes through:
    gateway.handle(text, teacher_id, files?) → GatewayResponse

The gateway handles:
  - Onboarding detection (new teacher? → onboard handler)
  - Intent detection (router.parse_intent)
  - Dispatch to the right handler
  - Event emission for TUI/monitoring
  - Session tracking

Transports (Telegram, Web, CLI) just render the GatewayResponse.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from clawed.config import has_config
from clawed.gateway_response import GatewayResponse
from clawed.handlers.export import ExportHandler
from clawed.handlers.feedback import FeedbackHandler
from clawed.handlers.gaps import GapsHandler
from clawed.handlers.generate import GenerateHandler
from clawed.handlers.ingest import IngestHandler
from clawed.handlers.misc import (
    DemoHandler,
    ModelSwitchHandler,
    PersonaHandler,
    ProgressHandler,
    SettingsHandler,
)
from clawed.handlers.onboard import OnboardHandler
from clawed.handlers.schedule import ScheduleHandler
from clawed.handlers.standards import StandardsHandler
from clawed.models import AppConfig
from clawed.router import Intent, parse_intent

logger = logging.getLogger(__name__)


@dataclass
class ActivityEvent:
    """A single event for the TUI activity feed."""
    timestamp: float
    event_type: str
    actor: str
    message: str
    data: dict = field(default_factory=dict)


@dataclass
class GatewayStats:
    """Live counters for the gateway dashboard."""
    messages_today: int = 0
    generations_today: int = 0
    errors_today: int = 0
    _start_time: float = field(default_factory=time.monotonic)

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time


class Gateway:
    """The brain of Claw-ED. Transport-agnostic."""

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.load()
        self._event_bus: asyncio.Queue[ActivityEvent] | None = None
        self.active_sessions: dict[str, dict] = {}
        self._stats = GatewayStats()
        self._running = False

        # Handlers
        self._onboard = OnboardHandler()
        self._generate = GenerateHandler()
        self._export = ExportHandler()
        self._feedback = FeedbackHandler()
        self._schedule = ScheduleHandler()
        self._gaps = GapsHandler()
        self._standards = StandardsHandler()
        self._ingest = IngestHandler()
        self._demo = DemoHandler()
        self._persona = PersonaHandler()
        self._settings = SettingsHandler()
        self._progress = ProgressHandler()
        self._model_switch = ModelSwitchHandler()

    @property
    def event_bus(self) -> asyncio.Queue[ActivityEvent]:
        """Lazily create the event bus queue (avoids Python 3.9 event loop issues)."""
        if self._event_bus is None:
            try:
                self._event_bus = asyncio.Queue(maxsize=500)
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
                self._event_bus = asyncio.Queue(maxsize=500)
        return self._event_bus

    async def handle(self, message: str, teacher_id: str,
                     files: list[Path] | None = None,
                     progress_callback=None) -> GatewayResponse:
        """Process any message from any transport."""
        self._stats.messages_today += 1
        self.active_sessions[teacher_id] = {
            "last_activity": datetime.now().isoformat(),
        }
        await self.emit("message_received", {
            "teacher_id": teacher_id,
            "text": message[:200],
        })

        try:
            if self._onboard.is_onboarding(teacher_id):
                return await self._onboard.step(teacher_id, message)

            if not has_config():
                return await self._onboard.step(teacher_id, message)

            return await self._dispatch(message, teacher_id, files,
                                         progress_callback=progress_callback)

        except Exception as e:
            logger.warning("Gateway error: %s", e)
            logger.debug("Gateway error detail: %s: %s", type(e).__name__, e)
            self._stats.errors_today += 1
            await self.emit("error", {"teacher_id": teacher_id, "message": str(e)})

            err = str(e).lower()
            if "401" in err or "unauthorized" in err or "api key" in err:
                return GatewayResponse(
                    text="Your AI provider key doesn't seem to be working. "
                         "Run `clawed setup --reset` to reconfigure it."
                )
            if "connection" in err or "connect" in err or "timeout" in err:
                return GatewayResponse(
                    text="Can't connect to your AI provider right now. "
                         "Check your internet connection and try again."
                )
            return GatewayResponse(
                text="Something went wrong. Try again, or run "
                     "`clawed setup --reset` to reconfigure."
            )

    async def handle_callback(self, callback_data: str, teacher_id: str) -> GatewayResponse:
        """Handle button press callbacks."""
        parts = callback_data.split(":")

        if parts[0] == "rate" and len(parts) >= 3:
            lesson_id = parts[1]
            rating_str = parts[2]
            if rating_str == "0_prompt":
                return self._feedback.rating_prompt(lesson_id)
            try:
                rating = int(rating_str)
            except ValueError:
                return GatewayResponse(text="Invalid rating.")
            return await self._feedback.rate(lesson_id, teacher_id, rating)

        if parts[0] == "action" and len(parts) >= 3:
            action = parts[1]
            lesson_id = parts[2]
            if action.startswith("export_"):
                fmt = action.replace("export_", "")
                return await self._export.export(lesson_id, teacher_id, fmt)
            if action == "worksheet":
                return await self._generate.lesson(f"worksheet for lesson {lesson_id}", teacher_id)

        return GatewayResponse(text="Unknown action.")

    async def stats(self) -> dict:
        """Return live stats. Kept async for backward compat."""
        s = self._stats
        return {
            "messages_today": s.messages_today,
            "generations_today": s.generations_today,
            "errors_today": s.errors_today,
            "uptime_seconds": s.uptime_seconds,
            "active_sessions": len(self.active_sessions),
        }

    async def _dispatch(self, message: str, teacher_id: str,
                        files: list[Path] | None = None,
                        progress_callback=None) -> GatewayResponse:
        """Route a message to the appropriate handler based on intent."""
        if files:
            return await self._ingest.handle(teacher_id, files,
                                             progress_callback=progress_callback)

        if self._looks_like_path(message):
            return await self._ingest.handle(teacher_id, path=message.strip(),
                                             progress_callback=progress_callback)

        # NOTE: parse_intent() is keyword/regex-based (zero cost).
        # When upgraded to LLM-based detection, use:
        #   from clawed.model_router import route
        #   config = route("intent_detection", self.config)
        parsed = parse_intent(message)
        intent = parsed.intent

        await self.emit("generation_started", {"teacher_id": teacher_id, "intent": intent.value})

        if intent == Intent.GENERATE_LESSON:
            self._stats.generations_today += 1
            return await self._generate.lesson(parsed.topic or message, teacher_id)

        if intent == Intent.GENERATE_UNIT:
            self._stats.generations_today += 1
            return await self._generate.unit(parsed.topic or message, teacher_id)

        if intent in (Intent.GENERATE_MATERIALS, Intent.GENERATE_ASSESSMENT,
                      Intent.GENERATE_BELLRINGER, Intent.GENERATE_DIFFERENTIATION,
                      Intent.GENERATE_YEAR_MAP, Intent.GENERATE_PACING_GUIDE):
            self._stats.generations_today += 1
            return await self._generate.lesson(message, teacher_id)

        if intent == Intent.SEARCH_STANDARDS:
            return await self._standards.lookup(parsed.subject or "", parsed.grade or "")

        if intent == Intent.EXPORT_PDF:
            return await self._export.export("last", teacher_id, "pdf")
        if intent == Intent.EXPORT_SLIDES:
            return await self._export.export("last", teacher_id, "slides")
        if intent == Intent.EXPORT_HANDOUT:
            return await self._export.export("last", teacher_id, "handout")
        if intent == Intent.EXPORT_DOC:
            return await self._export.export("last", teacher_id, "doc")

        if intent == Intent.GAP_ANALYSIS:
            return await self._gaps.analyze(teacher_id)
        if intent == Intent.SCHEDULE:
            return await self._schedule.show(teacher_id)
        if intent == Intent.DEMO:
            return await self._demo.run(teacher_id)
        if intent == Intent.SHOW_PERSONA:
            return await self._persona.show(teacher_id)
        if intent == Intent.SHOW_SETTINGS:
            return await self._settings.show(teacher_id)
        if intent == Intent.SHOW_PROGRESS:
            return await self._progress.show(teacher_id)
        if intent == Intent.SHOW_FEEDBACK:
            return await self._feedback.summary(teacher_id)
        if intent == Intent.SWITCH_MODEL:
            return await self._model_switch.switch(teacher_id, message)

        if intent == Intent.HELP:
            return self._help_response()
        if intent == Intent.SHOW_STATUS:
            return await self._status_response(teacher_id)
        if intent == Intent.SETUP:
            return await self._onboard.step(teacher_id, message)

        return await self._chat(message, teacher_id)

    async def _chat(self, message: str, teacher_id: str) -> GatewayResponse:
        """Conversational agent with tool use for freeform chat."""
        try:
            from clawed.agent import run_agent
            from clawed.model_router import route
            from clawed.state import TeacherSession

            session = TeacherSession.load(teacher_id)
            is_new_user = session.is_new

            if is_new_user:
                system = (
                    "You are Claw-ED, a warm and friendly AI teaching assistant for K-12 teachers. "
                    "This is your FIRST conversation with this teacher. Your job is to learn about "
                    "them through natural conversation.\n\n"
                    "CONVERSATION FLOW (ask ONE question at a time, 2-3 sentences max):\n"
                    "1. Introduce yourself warmly and ask their name\n"
                    "2. Ask what they teach (subject and grade level)\n"
                    "3. Ask what state they're in (for standards alignment)\n"
                    "4. Ask if they'd like to give you a nickname (suggest fun ones like 'Coach', "
                    "'Professor', or they can keep 'Claw-ED')\n"
                    "5. Ask if they have existing lesson plans you can learn from "
                    "(folder path like ~/Documents/Lessons)\n\n"
                    "TOOLS:\n"
                    "- Once you know their name, subject, grade, and state: call configure_profile\n"
                    "- If they give a folder path: call ingest_folder\n"
                    "- You can call configure_profile even if you only have name + subject — "
                    "grade and state are optional\n\n"
                    "TONE: Warm, casual, encouraging — like a friendly colleague in the teacher's "
                    "lounge. Use contractions. Keep it brief.\n\n"
                    "IMPORTANT: If the user's message is just 'hello' or a greeting, this means "
                    "the chat session just started. Respond with your introduction — don't just "
                    "say 'hi' back. Example first message:\n"
                    "'Hey there! I'm Claw-ED, your new AI teaching assistant. \U0001f393 "
                    "I'm here to help you plan lessons, build units, and create materials — "
                    "all in your teaching style. What's your name?'"
                )
            else:
                persona_context = (
                    session.persona.to_prompt_context()
                    if session.persona
                    else "Teacher persona not yet configured."
                )
                system = (
                    "You are Claw-ED, a warm and friendly AI teaching assistant. "
                    "You speak naturally and conversationally -- like a supportive colleague "
                    "in the teacher's lounge, not a corporate chatbot. Use contractions, "
                    "be personable, ask follow-up questions when helpful.\n\n"
                    "Keep responses concise: 1-3 sentences for casual chat (greetings, "
                    "small talk, simple questions). Only give longer responses when the "
                    "teacher asks for actual content generation or detailed curriculum help.\n\n"
                    "You have access to tools for generating lessons, looking up standards, "
                    "reading files, and more. Use them when the teacher's request needs action.\n\n"
                    f"{persona_context}"
                )

            config = route("quick_answer", self.config)
            history = session.get_context_for_llm(max_turns=4)

            response = await run_agent(
                message=message,
                system=system,
                teacher_id=teacher_id,
                config=config,
                conversation_history=history,
            )

            # Save to conversation context
            session.add_context("user", message)
            session.add_context("assistant", response[:500])
            session.save()

            return GatewayResponse(text=response)
        except Exception as e:
            logger.error("Agent chat failed: %s", e)
            # Fall back to simple generation
            try:
                from clawed.generation import generate_freeform
                from clawed.state import TeacherSession as FallbackSession
                session = FallbackSession.load(teacher_id)
                response = await generate_freeform(message, session)
                return GatewayResponse(text=response)
            except Exception as e2:
                logger.error("Fallback chat also failed: %s", e2)
                return GatewayResponse(text="I couldn't process that. Please try again.")

    def _help_response(self) -> GatewayResponse:
        return GatewayResponse(
            text=(
                "Here's what I can do:\n\n"
                "  'plan a unit on [topic]' — create a multi-week unit\n"
                "  'lesson on [topic]' — generate a daily lesson\n"
                "  'make a worksheet' — create student materials\n"
                "  'standards for [subject] [grade]' — look up standards\n"
                "  'curriculum gaps' — find what you're missing\n"
                "  'export slides/handout/doc' — export last lesson\n\n"
                "Just type naturally — I'll figure out what you need."
            ),
        )

    async def _status_response(self, teacher_id: str) -> GatewayResponse:
        try:
            from clawed.hermes_plugin import _show_status
            from clawed.state import TeacherSession
            session = TeacherSession.load(teacher_id)
            return GatewayResponse(text=_show_status(session))
        except Exception as e:
            return GatewayResponse(text=f"Could not load status: {e}")

    @staticmethod
    def _looks_like_path(text: str) -> bool:
        stripped = text.strip()
        return (
            stripped.startswith("/") and not stripped.startswith("/help")
            and not stripped.startswith("/start")
            and not stripped.startswith("/status")
            and "/" in stripped[1:]
        ) or stripped.startswith("~/")

    async def emit(self, event_type: str, data: dict | None = None) -> None:
        """Emit an event for TUI consumption. Public for backward compat."""
        event = ActivityEvent(
            timestamp=time.time(),
            event_type=event_type,
            actor=data.get("teacher_id", "system") if data else "system",
            message=data.get("text", data.get("message", event_type)) if data else event_type,
            data=data or {},
        )
        if self.event_bus.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.event_bus.get_nowait()
        await self.event_bus.put(event)

    # Backward compatibility
    async def process_message(self, text: str, teacher_id: str = "cli",
                              teacher_name: str = "Teacher") -> str:
        """Backward-compatible: process message and return text string."""
        r = await self.handle(text, teacher_id)
        return r.text

    async def start(self) -> None:
        """Backward-compatible start (no-op — transports start themselves)."""
        self._running = True
        await self.emit("system", {"message": "Gateway started"})

    async def stop(self) -> None:
        """Shut down the gateway."""
        self._running = False
        await self.emit("system", {"message": "Gateway stopped"})


EduAgentGateway = Gateway
