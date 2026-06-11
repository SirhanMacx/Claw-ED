"""Agent-first Gateway — control-plane pre-router + agent loop.

This replaces the legacy intent-router Gateway with an agent loop.
Deterministic paths (file ingestion, onboarding, approval callbacks)
are handled without touching the LLM. Only natural-language messages
go through the agent tool-use loop.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from clawed._legacy_gateway import ActivityEvent, GatewayStats
from clawed.agent_core.approvals import ApprovalManager
from clawed.agent_core.context import AgentContext
from clawed.agent_core.loop import LLMInterface, run_agent_loop
from clawed.agent_core.prompt import build_system_prompt
from clawed.agent_core.tools.base import ToolRegistry
from clawed.config import has_config, has_teacher_profile
from clawed.gateway_response import GatewayResponse
from clawed.models import AppConfig

logger = logging.getLogger(__name__)


_tool_lock = threading.Lock()


class _LLMClientAdapter:
    """Adapts the existing clawed.agent module's LLM calling to LLMInterface.

    Instead of re-implementing API calls, wraps the existing
    ``_call_with_native_tools`` / ``_call_with_ollama_tools`` functions
    from ``clawed.agent``.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str = "",
    ) -> dict[str, Any]:
        # The legacy agent functions operate on the global TOOL_DEFINITIONS.
        # We temporarily swap them under a lock so concurrent requests don't
        # clobber each other's tool definitions.
        import clawed.agent as _agent_mod
        from clawed.agent import _call_with_native_tools, _call_with_ollama_tools
        from clawed.models import LLMProvider

        with _tool_lock:
            original_defs = _agent_mod.TOOL_DEFINITIONS  # type: ignore[attr-defined]  # runtime-patched module global
            _agent_mod.TOOL_DEFINITIONS = tools or []  # type: ignore[attr-defined]  # runtime-patched module global
        try:
            if self._config.provider in (
                LLMProvider.ANTHROPIC, LLMProvider.OPENAI, LLMProvider.OPENROUTER,
            ):
                return await _call_with_native_tools(messages, system, self._config)
            else:
                return await _call_with_ollama_tools(messages, system, self._config)
        finally:
            with _tool_lock:
                _agent_mod.TOOL_DEFINITIONS = original_defs  # type: ignore[attr-defined]  # runtime-patched module global


class Gateway:
    """Agent-first Gateway — sits behind the feature-flag shim."""

    def __init__(self, config: AppConfig | None = None, llm: LLMInterface | None = None):
        self.config = config or AppConfig.load()
        self._event_bus: asyncio.Queue[ActivityEvent] | None = None
        self.active_sessions: dict[str, dict[str, Any]] = {}
        self._stats = GatewayStats()
        self._running = False
        self._llm = llm  # Injectable for testing

        # Control-plane handlers (reuse existing deterministic handlers)
        from clawed.handlers.ingest import IngestHandler
        from clawed.handlers.onboard import OnboardHandler

        self._ingest = IngestHandler()
        self._onboard = OnboardHandler()

        # Eagerly initialize databases so they're never left as 0-byte files
        try:
            from clawed.state import init_db as init_state_db
            init_state_db()
        except Exception as e:
            logger.debug("Eager init failed for state DB: %s", e)
            pass
        try:
            from clawed.agent_core.memory.sessions import (
                _ensure_db as init_sessions_db,
            )
            init_sessions_db()
        except Exception as e:
            logger.debug("Eager init failed for sessions DB: %s", e)
            pass
        try:
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB
            CurriculumKB()  # Creates DB + tables on init
        except Exception as e:
            logger.debug("Eager init failed for curriculum KB: %s", e)
            pass
        try:
            from clawed.agent_core.quality import _ensure_db as init_quality_db
            init_quality_db()
        except Exception as e:
            logger.debug("Eager init failed for quality DB: %s", e)
            pass

        # Agent subsystems
        self._approval_manager = ApprovalManager()
        self._registry = ToolRegistry()
        self._registry.discover(Path(__file__).parent / "tools")

        # Load custom teacher tools from ~/.eduagent/tools/
        import os

        custom_tools_dir = Path(
            os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
        ) / "tools"
        self._registry.discover_custom(custom_tools_dir)

        # Callback handlers for deterministic paths
        from clawed.handlers.export import ExportHandler
        from clawed.handlers.feedback import FeedbackHandler

        self._export = ExportHandler()
        self._feedback = FeedbackHandler()

    @property
    def event_bus(self) -> asyncio.Queue[ActivityEvent]:
        """Lazily create the event bus queue (avoids Python 3.9 event loop issues)."""
        if self._event_bus is None:
            try:
                self._event_bus = asyncio.Queue(maxsize=500)
            except RuntimeError:
                # Python 3.9: no event loop in sync context — create one
                asyncio.set_event_loop(asyncio.new_event_loop())
                self._event_bus = asyncio.Queue(maxsize=500)
        return self._event_bus

    # ------------------------------------------------------------------
    # Public interface (matches legacy Gateway exactly)
    # ------------------------------------------------------------------

    async def handle(
        self,
        message: str,
        teacher_id: str,
        files: list[Path] | None = None,
        progress_callback: Any = None,
        transport: str = "cli",
        event_callback: Any = None,
    ) -> GatewayResponse:
        """Process any message from any transport."""
        # Normalize teacher_id so CLI, Telegram, and MCP all share one brain
        from clawed.agent_core.identity import get_teacher_id
        teacher_id = get_teacher_id()
        self._last_transport = transport

        self._stats.messages_today += 1
        self.active_sessions[teacher_id] = {
            "last_activity": datetime.now().isoformat(),
        }
        await self.emit("message_received", {
            "teacher_id": teacher_id,
            "text": message[:200],
        })

        try:
            # 1. Files → ingest (deterministic, no LLM, runs in background)
            if files:
                return await self._ingest.handle(
                    teacher_id, files, progress_callback=progress_callback
                )

            # 2. Onboarding state machine (deterministic, no LLM)
            if self._onboard.is_onboarding(teacher_id):
                result = await self._onboard.step(teacher_id, message)
                # Save onboarding turns so Ed remembers the conversation
                try:
                    from clawed.agent_core.memory.sessions import save_turn
                    save_turn(teacher_id, "user", message, transport=transport)
                    save_turn(teacher_id, "assistant", result.text, transport=transport)
                except Exception as e:
                    logger.debug("Failed to save onboarding turn: %s", e)
                    pass
                return result

            # 3. First-run detection — no config at all
            if not has_config():
                if message.strip().lower() in ("/setup", "/start", "setup", "start"):
                    result = await self._onboard.step(teacher_id, message)
                    try:
                        from clawed.agent_core.memory.sessions import save_turn
                        save_turn(teacher_id, "user", message, transport=transport)
                        save_turn(teacher_id, "assistant", result.text, transport=transport)
                    except Exception as e:
                        logger.debug("Failed to save first-run turn: %s", e)
                        pass
                    return result
                return GatewayResponse(
                    text="Welcome to Claw-ED! I'm your personal teaching assistant. "
                    "Send /setup to configure your profile and API key, "
                    "or send /demo to see what I can do."
                )

            # 3b. Config exists but teacher hasn't completed profile setup
            # (quick_model_setup set the API key but conversational onboarding
            # hasn't collected name, subjects, grades, state yet)
            if not has_teacher_profile():
                return await self._onboard.step(teacher_id, message)

            # 4. /models command — interactive model selector
            if message.strip().lower() in ("/models", "/model", "models"):
                return self._handle_models_command()

            # 5. Natural-language → agent loop
            return await self._agent_loop(
                message, teacher_id,
                progress_callback=progress_callback,
                event_callback=event_callback,
            )

        except Exception as e:
            logger.error("Agent error for teacher %s: %s", teacher_id, e, exc_info=True)
            self._stats.errors_today += 1
            await self.emit("error", {"teacher_id": teacher_id, "message": str(e)})

            # Teacher-friendly error messages (no internal details exposed)
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
            if "rate limit" in err or "429" in err:
                return GatewayResponse(
                    text="Your AI provider is temporarily overloaded. "
                         "Wait a minute and try again."
                )
            return GatewayResponse(
                text="Something went wrong. Please try again."
            )

    async def handle_callback(self, callback_data: str, teacher_id: str) -> GatewayResponse:
        """Handle button press callbacks (approval, rate, export, model, etc.)."""
        parts = callback_data.split(":")

        # Model selection callbacks
        if parts[0] in ("models", "setmodel"):
            return await self.handle_model_callback(callback_data, teacher_id)

        # Approval callbacks
        if parts[0] == "approve" and len(parts) >= 2:
            approval_id = parts[1]
            pa = self._approval_manager.approve(approval_id)
            if pa:
                return GatewayResponse(text=f"Approved: {pa.action_description}")
            return GatewayResponse(text="Approval not found or already processed.")

        if parts[0] == "reject" and len(parts) >= 2:
            approval_id = parts[1]
            pa = self._approval_manager.reject(approval_id)
            if pa:
                return GatewayResponse(text=f"Rejected: {pa.action_description}")
            return GatewayResponse(text="Approval not found or already processed.")

        # Legacy rating callbacks
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

        # Legacy action callbacks
        if parts[0] == "action" and len(parts) >= 3:
            action = parts[1]
            lesson_id = parts[2]
            if action.startswith("export_"):
                fmt = action.replace("export_", "")
                return await self._export.export(lesson_id, teacher_id, fmt)

        return GatewayResponse(text="Unknown action.")

    async def stats(self) -> dict[str, Any]:
        """Return live stats. Kept async for backward compat."""
        s = self._stats
        return {
            "messages_today": s.messages_today,
            "generations_today": s.generations_today,
            "errors_today": s.errors_today,
            "uptime_seconds": s.uptime_seconds,
            "active_sessions": len(self.active_sessions),
        }

    async def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
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

    # Backward compatibility methods

    async def process_message(
        self, text: str, teacher_id: str = "cli", teacher_name: str = "Teacher",
    ) -> str:
        """Backward-compatible: process message and return text string."""
        r = await self.handle(text, teacher_id)
        return r.text

    async def start(self) -> None:
        """Backward-compatible start (no-op -- transports start themselves)."""
        self._running = True
        await self.emit("system", {"message": "Gateway started"})

    async def stop(self) -> None:
        """Shut down the gateway."""
        self._running = False
        await self.emit("system", {"message": "Gateway stopped"})

    async def handle_system_event(
        self,
        event_type: str,
        teacher_id: str = "local-teacher",
        payload: dict[str, Any] | None = None,
    ) -> GatewayResponse:
        """Handle a system event (scheduled task, cron trigger, etc.).

        Routes through the agent loop with context about what triggered it.
        """
        await self.emit(event_type, payload or {})

        # Build a descriptive message for the agent
        task_name = (payload or {}).get("task_name", event_type)
        message = (
            f"[SYSTEM] Scheduled task '{task_name}' has fired. "
            "Check what needs to be done and take action."
        )

        try:
            return await self._agent_loop(message, teacher_id)
        except Exception as e:
            logger.error("System event handling failed: %s", e)
            return GatewayResponse(
                text=f"System event '{event_type}' received but could not be processed: {e}",
            )

    # ------------------------------------------------------------------
    # Agent loop — the core reasoning path
    # ------------------------------------------------------------------

    def _load_teacher_context(self, teacher_id: str, message: str) -> tuple[Any, Any, Any, Any, Any, str, str]:
        """Load teacher profile, persona, memory, and session history.

        Returns (teacher_profile, persona_dict, memory_ctx, session_history,
                 recent_conversation, teacher_name, identity_summary).
        """
        teacher_profile = self._load_teacher_profile()
        persona_dict = self._load_persona(teacher_profile)

        from clawed.agent_core.memory.sessions import format_for_prompt, load_recent_for_llm
        session_history = load_recent_for_llm(teacher_id, limit=10)
        recent_conversation = format_for_prompt(teacher_id, limit=10)

        from clawed.agent_core.memory.loader import load_memory_context
        memory_ctx = load_memory_context(teacher_id, message)

        teacher_name = (
            (persona_dict or {}).get("name")
            or (teacher_profile or {}).get("name")
            or "Teacher"
        )

        identity_summary = ""
        if persona_dict:
            parts = []
            if persona_dict.get("subject_area"):
                parts.append(persona_dict["subject_area"])
            if persona_dict.get("grade_levels"):
                parts.append(f"grades {', '.join(persona_dict['grade_levels'])}")
            if persona_dict.get("teaching_style"):
                style = persona_dict["teaching_style"]
                if isinstance(style, str):
                    parts.append(style.replace("_", " "))
            identity_summary = ", ".join(parts)

        return (teacher_profile, persona_dict, memory_ctx, session_history,
                recent_conversation, teacher_name, identity_summary)

    def _build_agent_system_prompt(
        self,
        teacher_name: str,
        identity_summary: str,
        memory_ctx: Any,
        recent_conversation: str,
        teacher_id: str,
    ) -> str:
        """Build the full system prompt with all context layers."""
        reading_report_context = ""
        try:
            from clawed.paths import workspace_dir
            report_path = workspace_dir() / "reading_report.md"
            if report_path.exists():
                reading_report_context = report_path.read_text(encoding="utf-8")[:1500]
        except Exception as e:
            logger.debug("Failed to load reading report: %s", e)

        soul_context = ""
        try:
            from clawed.paths import workspace_dir as _ws_dir
            soul_path = _ws_dir() / "soul.md"
            if soul_path.exists():
                soul_context = soul_path.read_text(encoding="utf-8")[:2000]
        except Exception as e:
            logger.debug("Failed to load SOUL.md: %s", e)

        agent_name = self.config.agent_name
        is_new_user = teacher_name == "Teacher" and not memory_ctx.get("identity_summary")
        system = build_system_prompt(
            agent_name=agent_name,
            teacher_name=teacher_name,
            identity_summary=memory_ctx["identity_summary"] or identity_summary,
            improvement_context=memory_ctx["improvement_context"],
            curriculum_summary=memory_ctx["curriculum_summary"],
            relevant_episodes=memory_ctx["relevant_episodes"],
            preferences=memory_ctx.get("preferences_summary", ""),
            autonomy_summary=memory_ctx.get("autonomy_summary", ""),
            curriculum_kb_context=memory_ctx.get("curriculum_kb_context", ""),
            tool_names=self._registry.tool_names(),
            is_new_user=is_new_user,
            reading_report=reading_report_context,
            soul_context=soul_context,
        )

        # 2c. Detect un-ingested materials — kick off background ingest
        try:
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB
            kb = CurriculumKB()
            kb_stats = kb.stats(teacher_id)
            materials_paths = getattr(
                self.config.teacher_profile, "materials_paths", []
            )
            if kb_stats["doc_count"] == 0 and materials_paths:
                self._maybe_background_ingest(materials_paths, teacher_id)
                paths_str = ", ".join(materials_paths)
                system += (
                    "\n\n=== Materials Status ===\n"
                    f"The teacher's materials at {paths_str} are being "
                    "ingested in the background. This may take several "
                    "minutes for large collections.\n"
                    "=== End Materials Status ===\n"
                )
            elif kb_stats["doc_count"] > 0:
                paths_str = ", ".join(materials_paths) if materials_paths else "unknown"
                system += (
                    f"\n\n=== Your Knowledge Base ===\n"
                    f"You have {kb_stats['doc_count']} documents and "
                    f"{kb_stats['chunk_count']} searchable sections.\n"
                    f"Materials folder: {paths_str}\n"
                    f"=== End KB ===\n"
                )
        except Exception:
            logger.debug("Failed to load curriculum KB stats", exc_info=True)

        if recent_conversation:
            system += (
                "\n\n=== Recent Conversation (across all devices) ===\n"
                f"{recent_conversation}\n"
                "=== End Recent Conversation ===\n"
                "You can reference what was said on other devices naturally \u2014 "
                "e.g. 'Earlier you mentioned...' without specifying the device.\n"
            )
        else:
            last_session = memory_ctx.get("last_session_summary", "")
            if last_session:
                system += (
                    "\n\n=== Last Session Context ===\n"
                    f"The teacher's last interaction was about: {last_session}\n"
                    "If this is a new conversation, greet them with continuity \u2014 e.g. "
                    '"Last time we worked on [topic]. Want to continue or start something new?"\n'
                    "=== End Last Session Context ===\n"
                )

        from clawed.agent_core.planner import build_planning_prompt, is_planning_request
        if is_planning_request(memory_ctx.get("_original_message", "")):
            system += build_planning_prompt()

        return system

    def _append_kb_and_ingest_status(self, system: str, teacher_id: str) -> str:
        """Append KB stats or background ingest status to system prompt."""
        try:
            from clawed.agent_core.memory.curriculum_kb import CurriculumKB
            kb = CurriculumKB()
            kb_stats = kb.stats(teacher_id)
            materials_paths = getattr(self.config.teacher_profile, "materials_paths", [])
            if kb_stats["doc_count"] == 0 and materials_paths:
                self._maybe_background_ingest(materials_paths, teacher_id)
                system += (
                    "\n\n=== Materials Status ===\n"
                    f"Materials at {', '.join(materials_paths)} are being ingested.\n"
                    "=== End Materials Status ===\n"
                )
            elif kb_stats["doc_count"] > 0:
                system += (
                    f"\n\n=== Your Knowledge Base ===\n"
                    f"{kb_stats['doc_count']} documents, {kb_stats['chunk_count']} chunks indexed.\n"
                    f"Use search_my_materials to find content.\n"
                    f"=== End KB ===\n"
                )
        except Exception as e:
            logger.debug("Failed to load curriculum KB stats: %s", e)
        return system

    def _save_post_loop_context(self, teacher_id: str, message: str, result: Any, transport: str) -> None:
        """Save conversation context and episodic memory after the agent loop."""
        from clawed.agent_core.memory.sessions import save_turn
        save_turn(teacher_id, "user", message, transport=transport)
        save_turn(teacher_id, "assistant", result.text, transport=transport)
        self._save_session_context(teacher_id, message, result.text)

        try:
            from clawed.agent_core.memory.episodes import EpisodicMemory
            mem = EpisodicMemory()
            episode_text = f"Teacher: {message}\nClaw-ED: {result.text[:500]}"
            mem.store(teacher_id, episode_text, metadata={
                "type": "interaction",
                "had_tool_calls": bool(result.files),
                "message_length": len(message),
            })
        except Exception as e:
            logger.debug("Failed to store episodic memory: %s", e)

        try:
            from clawed.memory_engine import maybe_compress_episodes
            maybe_compress_episodes(teacher_id)
        except Exception as e:
            logger.debug("Failed to compress episodes: %s", e)

        try:
            from clawed.agent_core.memory.session_compress import maybe_compress_sessions
            maybe_compress_sessions(teacher_id)
        except Exception as e:
            logger.debug("Failed to compress sessions: %s", e)

    async def _agent_loop(
        self, message: str, teacher_id: str,
        progress_callback: Any = None, event_callback: Any = None,
    ) -> GatewayResponse:
        """Load context, build prompt, and run the agent tool-use loop."""
        transport = getattr(self, "_last_transport", "cli")

        (teacher_profile, persona_dict, memory_ctx, session_history,
         recent_conversation, teacher_name, identity_summary) = self._load_teacher_context(teacher_id, message)

        # Store original message for planning detection
        memory_ctx["_original_message"] = message

        system = self._build_agent_system_prompt(
            teacher_name, identity_summary, memory_ctx, recent_conversation, teacher_id,
        )

        system = self._append_kb_and_ingest_status(system, teacher_id)

        agent_name = self.config.agent_name

        # 3. Build AgentContext for tools
        context = AgentContext(
            teacher_id=teacher_id,
            config=self.config,
            teacher_profile=teacher_profile or {},
            persona=persona_dict,
            session_history=session_history,
            improvement_context=memory_ctx["improvement_context"],
            agent_name=agent_name,
            progress_callback=progress_callback,
            event_callback=event_callback,
        )

        # 4. Get or create LLM adapter
        llm = self._llm or _LLMClientAdapter(self.config)

        # 5. Run the agent loop
        await self.emit("generation_started", {
            "teacher_id": teacher_id,
            "intent": "agent_loop",
        })

        result = await run_agent_loop(
            message=message,
            system=system,
            context=context,
            llm=llm,
            registry=self._registry,
            max_iterations=self.config.max_agent_iterations,
            conversation_history=session_history,
        )

        # 6. Save conversation context and episodic memory
        self._save_post_loop_context(teacher_id, message, result, transport)

        return result

    # ------------------------------------------------------------------
    # /models command
    # ------------------------------------------------------------------

    def _handle_models_command(self) -> GatewayResponse:
        """Interactive model selector — returns provider list with buttons."""
        from clawed.gateway_response import Button

        current = self.config.provider.value
        model_map = {
            "ollama": self.config.ollama_model,
            "anthropic": self.config.anthropic_model,
            "openai": self.config.openai_model,
            "google": self.config.google_model,
            "openrouter": self.config.openrouter_model,
        }
        current_model = model_map.get(current, "unknown")

        text = (
            f"Current: **{current_model}** ({current})\n\n"
            "Choose a provider to see available models:"
        )
        buttons = [
            Button(label="Ollama Cloud", callback_data="models:ollama"),
            Button(label="OpenRouter", callback_data="models:openrouter"),
            Button(label="Anthropic", callback_data="models:anthropic"),
            Button(label="OpenAI", callback_data="models:openai"),
            Button(label="Google", callback_data="models:google"),
        ]
        return GatewayResponse(
            text=text,
            button_rows=[buttons[:3], buttons[3:]],
        )

    async def handle_model_callback(
        self, callback_data: str, teacher_id: str,
    ) -> GatewayResponse:
        """Handle model selection callbacks from Telegram buttons."""
        from clawed.gateway_response import Button

        parts = callback_data.split(":")
        if len(parts) < 2:
            return GatewayResponse(text="Invalid selection.")

        action = parts[0]  # "models" or "setmodel"
        provider = parts[1] if len(parts) > 1 else ""
        model_name = parts[2] if len(parts) > 2 else ""

        if action == "models" and provider and not model_name:
            # Show models for this provider
            from clawed.model_discovery import list_all_models
            all_models = list_all_models(self.config)
            models = all_models.get(provider, [])

            if not models:
                return GatewayResponse(
                    text=f"No models found for {provider}.",
                )

            current = getattr(
                self.config, f"{provider}_model", "",
            )
            buttons = []
            for m in models[:12]:  # Cap at 12 buttons
                name = m.get("name") or m.get("id", "?")
                label = name
                if name == current:
                    label = f"{name} ✓"
                buttons.append(Button(
                    label=label[:30],
                    callback_data=f"setmodel:{provider}:{name}",
                ))

            # Arrange in rows of 2
            rows = []
            for i in range(0, len(buttons), 2):
                rows.append(buttons[i:i + 2])

            return GatewayResponse(
                text=f"**{provider.title()}** models:",
                button_rows=rows,
            )

        if action == "setmodel" and provider and model_name:
            # Switch to selected model
            from clawed.models import AppConfig, LLMProvider
            cfg = AppConfig.load()

            try:
                cfg.provider = LLMProvider(provider)
            except ValueError:
                return GatewayResponse(
                    text=f"Unknown provider: {provider}",
                )

            field = f"{provider}_model"
            if hasattr(cfg, field):
                setattr(cfg, field, model_name)
            cfg.save()

            return GatewayResponse(
                text=f"Switched to **{model_name}** ({provider}).",
            )

        return GatewayResponse(text="Unknown model action.")

    # ------------------------------------------------------------------
    # Background ingest
    # ------------------------------------------------------------------

    _ingest_started: bool = False

    def _maybe_background_ingest(
        self, materials_paths: list[str], teacher_id: str
    ) -> None:
        """Start a background thread to ingest materials. Runs once per process."""
        if Gateway._ingest_started:
            return
        Gateway._ingest_started = True

        import threading

        def _do_ingest() -> None:
            import asyncio
            for path_str in materials_paths:
                try:
                    from pathlib import Path
                    p = Path(path_str).expanduser()
                    if not p.exists():
                        continue
                    logger.info("Background ingest starting: %s", p)
                    from clawed.ingestor import ingest_path
                    result = ingest_path(p)
                    # ingest_path may return a list or coroutine
                    docs = asyncio.run(result) if asyncio.iscoroutine(result) else result
                    if docs:
                        from clawed.agent_core.memory.curriculum_kb import (
                            CurriculumKB,
                        )
                        kb = CurriculumKB()
                        for doc in docs:
                            try:
                                doc_type = (
                                    doc.doc_type.value
                                    if hasattr(doc.doc_type, "value")
                                    else str(doc.doc_type)
                                )
                                kb.index(
                                    teacher_id=teacher_id,
                                    doc_title=doc.title,
                                    source_path=doc.source_path or "",
                                    full_text=doc.content,
                                    metadata={"doc_type": doc_type},
                                )
                            except Exception as e:
                                logger.debug("Chunk index failed: %s", e)
                        logger.info(
                            "Background ingest done: %d docs from %s",
                            len(docs), p,
                        )
                except Exception as e:
                    logger.warning("Background ingest failed for %s: %s", path_str, e)

        thread = threading.Thread(target=_do_ingest, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Context loading helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_teacher_profile() -> dict[str, Any] | None:
        """Load teacher profile from database OR config.json.

        The CLI onboarding saves to config.json (teacher_profile key).
        The Telegram bot reads from the database. We check both so
        the two systems share the same teacher identity.
        """
        # 1. Try the database first (Telegram bot's canonical store)
        try:
            from clawed.database import Database
            db = Database()
            profile = db.get_default_teacher()
            if profile and profile.get("name"):
                return profile
        except Exception as e:
            logger.debug("Could not load teacher from DB: %s", e)

        # 2. Fall back to config.json (CLI onboarding saves here)
        try:
            from clawed.models import AppConfig
            config = AppConfig.load()
            tp = config.teacher_profile
            if tp and (tp.name or tp.subjects or tp.grade_levels):
                return {
                    "name": tp.name or "Teacher",
                    "subjects": tp.subjects or [],
                    "grade_levels": tp.grade_levels or [],
                    "state": tp.state or "",
                }
        except Exception as e:
            logger.debug("Could not load teacher from config: %s", e)

        return None

    @staticmethod
    def _load_persona(teacher_profile: dict[str, Any] | None) -> dict[str, Any] | None:
        """Parse persona from teacher profile's persona_json field."""
        if not teacher_profile or not teacher_profile.get("persona_json"):
            return None
        try:
            parsed: dict[str, Any] = json.loads(teacher_profile["persona_json"])
            return parsed
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug("Could not parse persona_json: %s", e)
            return None

    @staticmethod
    def _load_session_history(teacher_id: str) -> list[dict[str, Any]]:
        """Load conversation history from TeacherSession."""
        try:
            from clawed.state import TeacherSession
            session = TeacherSession.load(teacher_id)
            return session.get_context_for_llm(max_turns=4)
        except Exception as e:
            logger.debug("Could not load session history: %s", e)
            return []

    @staticmethod
    def _load_improvement_context() -> str:
        """Load improvement context from the memory engine."""
        try:
            from clawed.memory_engine import build_improvement_context
            return build_improvement_context()
        except Exception as e:
            logger.debug("Could not load improvement context: %s", e)
            return ""

    @staticmethod
    def _save_session_context(teacher_id: str, user_msg: str, assistant_msg: str) -> None:
        """Save conversation turn to TeacherSession."""
        try:
            from clawed.state import TeacherSession
            session = TeacherSession.load(teacher_id)
            session.add_context("user", user_msg)
            session.add_context("assistant", assistant_msg[:500])
            session.save()
        except Exception as e:
            logger.debug("Could not save session context: %s", e)
