"""Tool: sub_packet — wraps clawed.sub_packet.generate_sub_packet."""
from __future__ import annotations

from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult


class SubPacketTool:
    """Generate a substitute teacher packet."""

    risk_level = "read_only"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "sub_packet",
                "description": (
                    "Generate a complete substitute teacher packet with "
                    "schedule, instructions, and emergency info."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "teacher_name": {
                            "type": "string",
                            "description": "The teacher's name",
                        },
                        "school": {
                            "type": "string",
                            "description": "School name",
                        },
                        "class_name": {
                            "type": "string",
                            "description": "Class name (e.g. 'Period 3 Math')",
                        },
                        "grade": {
                            "type": "string",
                            "description": "Grade level",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Subject area",
                        },
                        "date": {
                            "type": "string",
                            "description": "Date of absence (e.g. '2025-03-15')",
                        },
                        "period_or_time": {
                            "type": "string",
                            "description": "Period or time block (e.g. '9:00-10:00')",
                        },
                        "lesson_topic": {
                            "type": "string",
                            "description": "Topic for the day's lesson (optional)",
                            "default": "",
                        },
                    },
                    "required": [
                        "teacher_name", "school", "class_name",
                        "grade", "subject", "date", "period_or_time",
                    ],
                },
            },
        }

    async def execute(
        self, params: dict[str, Any], context: AgentContext
    ) -> ToolResult:
        from clawed.llm import LLMClient
        from clawed.sub_packet import (
            SubPacketRequest,
            generate_sub_packet,
            sub_packet_to_markdown,
        )

        try:
            request = SubPacketRequest(
                teacher_name=params["teacher_name"],
                school=params["school"],
                class_name=params["class_name"],
                grade=params["grade"],
                subject=params["subject"],
                date=params["date"],
                period_or_time=params["period_or_time"],
                lesson_topic=params.get("lesson_topic", ""),
            )
            llm = LLMClient(context.config)
            packet = await generate_sub_packet(request, llm)
            packet_data = packet.model_dump()
            # Convert datetime for JSON serialization
            if "generated_at" in packet_data:
                packet_data["generated_at"] = str(packet_data["generated_at"])
            md = sub_packet_to_markdown(packet)
            return ToolResult(
                text=f"Generated sub packet for {params['date']}:\n\n{md[:2000]}",
                data=packet_data,
                side_effects=[f"Generated sub packet for {params['date']}"],
            )
        except Exception as e:
            return ToolResult(text=f"Failed to generate sub packet: {e}")
