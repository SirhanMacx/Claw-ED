"""Tools: get_style_profile / set_active_profile — manage the teacher's
learned STYLE PROFILES (built by ingest_materials).

Multi-profile: a teacher may keep one profile per course ("Global 10",
"AP Psych"). Exactly one is active at a time, or none — the default
MacxLabs style. Profiles live on disk in the agent's data dir; switching
them only flips a local pointer, so these tools are cheap and safe.
"""
from __future__ import annotations

import logging
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import RISK_READ_ONLY, RISK_WRITE_LOCAL

logger = logging.getLogger(__name__)


def _profile_summary(profile: Any, active: bool) -> str:
    """Human-readable card for one profile."""
    from clawed.style_profile import StyleProfile

    assert isinstance(profile, StyleProfile)
    lines = [
        f"### {profile.name} {'(ACTIVE)' if active else ''}".rstrip(),
        f"- id: {profile.profile_id} · learned from {profile.files_analyzed} "
        f"file(s) in {profile.source_path}",
    ]
    if profile.voice_description:
        lines.append(f"- Voice: {profile.voice_description}")
    if profile.structure_summary:
        lines.append(f"- Structure: {profile.structure_summary}")
    sections = [
        f"{s.name} ({s.frequency:.0%})"
        for s in profile.lesson_structure if s.frequency >= 0.2
    ]
    if sections:
        lines.append(f"- Recurring sections: {', '.join(sections[:8])}")
    if profile.question_types:
        lines.append(f"- Assessments: {', '.join(profile.question_types[:5])}")
    if profile.answer_key_style:
        lines.append(f"- Answer keys: {profile.answer_key_style}")
    if profile.scaffolds:
        lines.append(f"- Scaffolds: {', '.join(profile.scaffolds[:6])}")
    return "\n".join(lines)


class GetStyleProfileTool:
    """Show the teacher's learned style profile(s)."""

    risk_level = RISK_READ_ONLY

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_style_profile",
                "description": (
                    "Show the teacher's learned STYLE PROFILE(s) — the voice, "
                    "lesson structure, and assessment conventions Claw-ED "
                    "learned from their own files via ingest_materials. "
                    "Lists all profiles and which one is active."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "profile_id": {
                            "type": "string",
                            "description": (
                                "Optional: a specific profile id. Omit to "
                                "list all profiles."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext,
    ) -> ToolResult:
        from clawed import style_profile as sp

        active_id = sp.get_active_profile_id()
        pid = str(params.get("profile_id") or "").strip()
        if pid:
            profile = sp.load_profile(pid)
            if profile is None:
                return ToolResult(text=f"No style profile with id '{pid}'.")
            return ToolResult(
                text=_profile_summary(profile, active=pid == active_id),
                data={"profile_id": pid, "active": pid == active_id},
            )

        profiles = sp.list_profiles()
        if not profiles:
            return ToolResult(
                text=(
                    "No style profiles yet. Run ingest_materials on a folder "
                    "of the teacher's lesson files to learn their style."
                ),
            )
        parts = [
            _profile_summary(p, active=p.profile_id == active_id)
            for p in profiles
        ]
        if active_id is None:
            parts.append(
                "_No profile is active — output uses the default "
                "MacxLabs style._"
            )
        return ToolResult(
            text="\n\n".join(parts),
            data={
                "profiles": [p.profile_id for p in profiles],
                "active": active_id,
            },
        )


class SetActiveProfileTool:
    """Switch which style profile conditions generation, or turn styling off."""

    # Flips a pointer inside the agent's own data dir — no teacher files
    # are touched — but it changes how everything generates, so it stays
    # behind the standard write_local approval.
    risk_level = RISK_WRITE_LOCAL

    @staticmethod
    def approval_description(params: dict[str, Any]) -> str:
        pid = str(params.get("profile_id") or "").strip()
        if pid and pid.lower() not in ("none", "off", "default"):
            return f"Switch the active style profile to '{pid}'"
        return "Turn the style profile off (default MacxLabs style)"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "set_active_profile",
                "description": (
                    "Switch which learned STYLE PROFILE conditions generated "
                    "lessons/assessments (a teacher may keep one per course), "
                    "or pass 'none' to turn styling off and use the default "
                    "MacxLabs style."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "profile_id": {
                            "type": "string",
                            "description": (
                                "The profile id to activate, or 'none' / "
                                "'off' / 'default' for the default style."
                            ),
                        },
                    },
                    "required": ["profile_id"],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext,
    ) -> ToolResult:
        from clawed import style_profile as sp

        pid = str(params.get("profile_id") or "").strip()
        if not pid or pid.lower() in ("none", "off", "default"):
            sp.set_active_profile(None)
            return ToolResult(
                text=(
                    "Style profile off — output now uses the default "
                    "MacxLabs style. The learned profiles are kept and can "
                    "be re-activated any time."
                ),
                data={"active": None},
                side_effects=["deactivated style profile"],
            )

        profile = sp.load_profile(pid)
        if profile is None:
            known = ", ".join(p.profile_id for p in sp.list_profiles()) or "(none)"
            return ToolResult(
                text=f"No style profile with id '{pid}'. Known profiles: {known}.",
            )
        sp.set_active_profile(pid)
        return ToolResult(
            text=(
                f"Style profile \"{profile.name}\" is now active — new "
                "lessons and assessments will match that voice."
            ),
            data={"active": pid},
            side_effects=[f"activated style profile {pid}"],
        )
