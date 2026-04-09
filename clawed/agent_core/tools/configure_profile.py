"""Tool: configure_profile — wraps teacher profile configuration."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult

logger = logging.getLogger(__name__)


class ConfigureProfileTool:
    """Configure the teacher's profile (name, subject, grade levels)."""

    risk_level = "write_local"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "configure_profile",
                "description": (
                    "Save or update the teacher's profile during onboarding. "
                    "Sets name, subject, grade levels, and state."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "teacher_name": {
                            "type": "string",
                            "description": "The teacher's name",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Primary subject area",
                        },
                        "grade_levels": {
                            "type": "string",
                            "description": "Comma-separated grade levels (e.g. '6,7,8')",
                            "default": "",
                        },
                        "state": {
                            "type": "string",
                            "description": "US state for state standards (e.g. 'NY')",
                            "default": "",
                        },
                        "agent_name": {
                            "type": "string",
                            "description": "What the teacher wants to call their AI partner (default: Claw-ED)",
                            "default": "",
                        },
                    },
                    "required": ["teacher_name", "subject"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.models import TeacherPersona, TeacherProfile
        from clawed.state import TeacherSession

        # Accept both "teacher_name" and "name" — LLMs sometimes use either key
        teacher_name = (
            params.get("teacher_name")
            or params.get("name")
            or params.get("teacher")
            or ""
        )
        subject = params.get("subject", "")
        grade_levels_str = params.get("grade_levels", params.get("grades", ""))
        state = params.get("state", "")
        agent_name = params.get("agent_name", "")

        if not teacher_name:
            return ToolResult(
                text="I need the teacher's name to save the profile. "
                     "Please ask the teacher their name first."
            )

        grades = [g.strip() for g in grade_levels_str.split(",") if g.strip()]

        try:
            import os as _os
            config = context.config

            if agent_name:
                config.agent_name = agent_name

            config.teacher_profile = TeacherProfile(
                name=teacher_name,
                subjects=[subject],
                grade_levels=grades,
                state=state,
            )
            config.save()

            # Mark onboarding as complete
            _data = _os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
            marker = Path(_data) / "workspace" / "onboarding_complete"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(f"Completed by {teacher_name}\n")

            # Auto-index state standards when state is provided
            side_effects = [f"Saved profile for {teacher_name}"]
            if state:
                try:
                    from clawed.state_standards import get_standards_context_for_prompt
                    standards_context = get_standards_context_for_prompt(
                        state,
                        [subject] if subject else [],
                        grades,
                    )
                    if standards_context:
                        side_effects.append(
                            f"Loaded {state} state standards for {subject}"
                        )
                except Exception:
                    pass

            persona = TeacherPersona(name=teacher_name, subject_area=subject)
            session = TeacherSession.load(context.teacher_id or "local-teacher")
            session.persona = persona
            session.save()

            try:
                from clawed.workspace import init_workspace
                init_workspace(persona, config)
            except Exception:
                pass

            # Update soul.md "Who I Am" section with identity
            try:
                _data = _os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
                soul_path = Path(_data) / "workspace" / "soul.md"
                soul_path.parent.mkdir(parents=True, exist_ok=True)

                identity_parts = [f"Name: {teacher_name}", f"Subject: {subject}"]
                if grades:
                    identity_parts.append(f"Grades: {', '.join(grades)}")
                if state:
                    identity_parts.append(f"State: {state}")
                identity_text = "\n" + "\n".join(f"- {p}" for p in identity_parts) + "\n"

                from clawed.agent_core.tools.update_soul import SOUL_TEMPLATE

                if soul_path.exists():
                    current = soul_path.read_text(encoding="utf-8")
                    if "## Who I Am" in current:
                        current = current.replace(
                            "## Who I Am", f"## Who I Am{identity_text}", 1
                        )
                    else:
                        current = f"## Who I Am{identity_text}\n" + current
                    soul_path.write_text(current, encoding="utf-8")
                else:
                    content = SOUL_TEMPLATE.replace(
                        "## Who I Am",
                        f"## Who I Am{identity_text}",
                        1,
                    )
                    soul_path.write_text(content, encoding="utf-8")
                side_effects.append("Updated SOUL.md with teacher identity")
            except Exception as e:
                logger.debug("SOUL.md identity update failed: %s", e)

            return ToolResult(
                text=f"Profile saved: {teacher_name}, {subject}"
                f"{', grades ' + grade_levels_str if grades else ''}.",
                data={
                    "teacher_name": teacher_name,
                    "subject": subject,
                    "grade_levels": grades,
                    "state": state,
                },
                side_effects=side_effects,
            )
        except Exception as e:
            return ToolResult(text=f"Failed to configure profile: {e}")
