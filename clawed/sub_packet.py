"""Sub packet generator — creates complete substitute teacher packets."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from clawed.llm import LLMClient


class SubPacketRequest(BaseModel):
    """Everything the generator needs to create a sub packet."""

    teacher_name: str
    school: str
    class_name: str
    grade: str
    subject: str
    date: str
    period_or_time: str
    lesson_topic: str = ""
    lesson_context: str = ""


class SubPacket(BaseModel):
    """A complete substitute teacher packet ready for printing."""

    teacher_name: str
    class_name: str
    grade: str
    subject: str
    date: str
    period_or_time: str
    overview: str
    daily_schedule: list[str] = Field(default_factory=list)
    lesson_instructions: list[str] = Field(default_factory=list)
    student_notes: str = ""
    materials_needed: list[str] = Field(default_factory=list)
    emergency_info: str = ""
    closing_notes: str = ""
    generated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("student_notes", mode="before")
    @classmethod
    def _coerce_student_notes(cls, v: Any) -> Any:
        if isinstance(v, list):
            return "\n".join(str(item) for item in v)
        return v

    @field_validator("emergency_info", mode="before")
    @classmethod
    def coerce_emergency_info(cls, v: Any) -> str:
        if isinstance(v, dict):
            return json.dumps(v)
        return str(v) if v else ""


_SYSTEM_PROMPT = (
    "You are writing a sub packet as if you are the teacher. "
    "Write explicit, step-by-step instructions that any substitute could follow. "
    "Be encouraging and professional."
)

_USER_PROMPT_TEMPLATE = """\
Generate a complete substitute teacher packet as JSON.

Teacher: {teacher_name}
School: {school}
Class: {class_name}
Grade: {grade}
Subject: {subject}
Date: {date}
Period/Time: {period_or_time}
{topic_line}{context_line}

Return a JSON object with these exact keys:
- "overview": A 2-3 sentence class overview for the substitute.
- "daily_schedule": A list of strings, each describing one block of the period \
(e.g. "0:00-5:00 — Attendance and warm-up").
- "lesson_instructions": A numbered list of strings — explicit, step-by-step \
instructions the substitute should follow. Be very detailed.
- "student_notes": General behavior/seating tips (no real student names). \
Example: "The class is generally well-behaved. The front row tends to finish \
early — have extension work ready."
- "materials_needed": A list of materials/handouts the sub will need.
- "emergency_info": Emergency contacts, nurse extension, office number, \
fire drill procedure — everything a sub needs in an emergency.
- "closing_notes": A friendly closing note from the teacher to the sub.

Return ONLY the JSON object, no markdown fences."""


async def generate_sub_packet(
    request: SubPacketRequest,
    llm: LLMClient,
) -> SubPacket:
    """Generate a complete substitute teacher packet via LLM."""
    topic_line = (
        f"Lesson Topic: {request.lesson_topic}\n" if request.lesson_topic else ""
    )
    context_line = (
        f"Unit/Context: {request.lesson_context}\n" if request.lesson_context else ""
    )

    prompt = _USER_PROMPT_TEMPLATE.format(
        teacher_name=request.teacher_name,
        school=request.school,
        class_name=request.class_name,
        grade=request.grade,
        subject=request.subject,
        date=request.date,
        period_or_time=request.period_or_time,
        topic_line=topic_line,
        context_line=context_line,
    )

    data = await llm.generate_json(
        prompt=prompt,
        system=_SYSTEM_PROMPT,
        temperature=0.5,
        max_tokens=4096,
    )

    return SubPacket(
        teacher_name=request.teacher_name,
        class_name=request.class_name,
        grade=request.grade,
        subject=request.subject,
        date=request.date,
        period_or_time=request.period_or_time,
        overview=data.get("overview", ""),
        daily_schedule=data.get("daily_schedule", []),
        lesson_instructions=data.get("lesson_instructions", []),
        student_notes=data.get("student_notes", ""),
        materials_needed=data.get("materials_needed", []),
        emergency_info=data.get("emergency_info", ""),
        closing_notes=data.get("closing_notes", ""),
    )


def sub_packet_to_markdown(packet: SubPacket) -> str:
    """Render a SubPacket as printable markdown with clear sections."""
    lines: list[str] = []
    lines.append(f"# Substitute Teacher Packet — {packet.class_name}")
    lines.append("")
    lines.append(f"**Teacher:** {packet.teacher_name}  ")
    lines.append(f"**Date:** {packet.date}  ")
    lines.append(f"**Class:** {packet.class_name}  ")
    lines.append(f"**Grade:** {packet.grade}  ")
    lines.append(f"**Subject:** {packet.subject}  ")
    lines.append(f"**Period/Time:** {packet.period_or_time}  ")
    lines.append("")

    lines.append("## Overview")
    lines.append("")
    lines.append(packet.overview)
    lines.append("")

    if packet.daily_schedule:
        lines.append("## Daily Schedule")
        lines.append("")
        for item in packet.daily_schedule:
            lines.append(f"- {item}")
        lines.append("")

    if packet.lesson_instructions:
        lines.append("## Lesson Instructions")
        lines.append("")
        for i, step in enumerate(packet.lesson_instructions, 1):
            # Strip any existing numbering the LLM may have added
            cleaned = step.lstrip("0123456789.) ").strip()
            lines.append(f"{i}. {cleaned if cleaned else step}")
        lines.append("")

    if packet.student_notes:
        lines.append("## Student & Classroom Notes")
        lines.append("")
        lines.append(packet.student_notes)
        lines.append("")

    if packet.materials_needed:
        lines.append("## Materials Needed")
        lines.append("")
        for item in packet.materials_needed:
            lines.append(f"- [ ] {item}")
        lines.append("")

    if packet.emergency_info:
        lines.append("## Emergency Information")
        lines.append("")
        lines.append(packet.emergency_info)
        lines.append("")

    if packet.closing_notes:
        lines.append("## Notes from the Teacher")
        lines.append("")
        lines.append(packet.closing_notes)
        lines.append("")

    lines.append("---")
    lines.append(
        f"*Generated by Claw-ED on {packet.generated_at.strftime('%Y-%m-%d %H:%M')}*"
    )
    return "\n".join(lines)


def save_sub_packet(packet: SubPacket, output_dir: Path | None = None) -> Path:
    """Save sub packet JSON and markdown to ~/.eduagent/sub_packets/."""
    from clawed.io import safe_filename, write_text

    if output_dir is None:
        from clawed.paths import data_dir
        output_dir = data_dir() / "sub_packets"
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_date = safe_filename(packet.date, max_len=50)
    safe_class = safe_filename(packet.class_name, max_len=50)
    stem = f"sub_packet_{safe_date}_{safe_class}"

    json_path = output_dir / f"{stem}.json"
    write_text(json_path, packet.model_dump_json(indent=2))

    md_path = output_dir / f"{stem}.md"
    write_text(md_path, sub_packet_to_markdown(packet))

    return md_path
