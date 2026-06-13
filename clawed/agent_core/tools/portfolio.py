"""Build advertising-safe sample portfolios from cleared lesson materials."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import RISK_WRITE_LOCAL
from clawed.paths import path_is_within, workspace_dir


class PortfolioBuildTool:
    """Create a sample portfolio folder from synthetic or cleared materials."""

    risk_level = RISK_WRITE_LOCAL

    @staticmethod
    def approval_description(params: dict[str, Any]) -> str:
        source_dir = str(params.get("source_dir") or "bundled sample curriculum")
        return (
            "Build an advertising-safe sample portfolio from cleared lesson "
            f"materials in {source_dir} and write the generated artifacts locally."
        )

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "portfolio_build",
                "description": (
                    "Build an advertising-safe sample portfolio from synthetic, "
                    "public-domain, or teacher-cleared lesson materials. Writes a "
                    "manifest, teacher lesson plan, student handout, assessment, "
                    "differentiation notes, parent note, and showcase copy into "
                    "the local Claw-ED workspace."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_dir": {
                            "type": "string",
                            "description": (
                                "Folder of cleared sample materials. Defaults to "
                                "examples/sample_curriculum in the repo."
                            ),
                        },
                        "topic": {
                            "type": "string",
                            "description": "Topic for the portfolio. Default: Industrial Revolution.",
                        },
                        "course": {
                            "type": "string",
                            "description": "Course/grade label. Default: Grade 9 Social Studies.",
                        },
                        "source_status": {
                            "type": "string",
                            "enum": ["synthetic", "public-domain", "teacher-cleared", "generated"],
                            "description": "Legal/source status for the input materials.",
                        },
                    },
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: AgentContext) -> ToolResult:
        repo_root = Path(__file__).resolve().parents[3]
        raw_source = str(params.get("source_dir") or "").strip()
        source_dir = (
            Path(raw_source).expanduser().resolve()
            if raw_source
            else (repo_root / "examples" / "sample_curriculum").resolve()
        )
        if not source_dir.exists() or not source_dir.is_dir():
            return ToolResult(text=f"Source folder not found: {source_dir}")

        # For safety, accept bundled repo examples or files under the teacher's home.
        home = Path.home().resolve()
        if not (path_is_within(source_dir, repo_root) or path_is_within(source_dir, home)):
            return ToolResult(text="Access denied: source_dir must be in the repo examples or your home folder.")

        topic = str(params.get("topic") or "Industrial Revolution").strip()
        course = str(params.get("course") or "Grade 9 Social Studies").strip()
        source_status = str(params.get("source_status") or "synthetic").strip()
        if source_status not in {"synthetic", "public-domain", "teacher-cleared", "generated"}:
            source_status = "synthetic"

        samples = self._read_samples(source_dir)
        if not samples:
            return ToolResult(text=f"No readable sample materials found in {source_dir}.")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = workspace_dir() / "sample_portfolios" / f"{self._slug(topic)}-{stamp}"
        out_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "title": f"{topic} Sample Portfolio",
            "course": course,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_status": source_status,
            "source_dir": str(source_dir),
            "sources": [
                {"title": title, "path": path, "characters_used": len(text)}
                for title, path, text in samples
            ],
            "provider_boundary": (
                "This baseline portfolio is generated locally from cleared sample "
                "materials. Model-enhanced portfolio runs may send excerpts to the "
                "teacher-configured provider."
            ),
        }

        files = {
            "manifest.json": json.dumps(manifest, indent=2),
            "teacher_lesson_plan.md": self._lesson_plan(topic, course, samples),
            "student_handout.md": self._student_handout(topic, samples),
            "assessment.md": self._assessment(topic, samples),
            "differentiation_notes.md": self._differentiation(topic, course),
            "parent_note.md": self._parent_note(topic, course),
            "advertising_showcase.md": self._showcase(topic, course, source_status),
        }

        written: list[Path] = []
        for name, content in files.items():
            path = out_dir / name
            path.write_text(content, encoding="utf-8")
            written.append(path)

        return ToolResult(
            text=(
                f"Built sample portfolio for {topic} in {out_dir}.\n"
                "Artifacts: teacher lesson plan, student handout, assessment, "
                "differentiation notes, parent note, advertising showcase, manifest."
            ),
            files=written,
            data={"output_dir": str(out_dir), "manifest": manifest},
            side_effects=[f"built-sample-portfolio:{out_dir}"],
        )

    @staticmethod
    def _read_samples(source_dir: Path) -> list[tuple[str, str, str]]:
        samples: list[tuple[str, str, str]] = []
        for path in sorted(source_dir.rglob("*")):
            if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                continue
            if not text:
                continue
            title = path.stem.replace("_", " ").replace("-", " ").title()
            samples.append((title, str(path), text[:2200]))
            if len(samples) >= 5:
                break
        return samples

    @staticmethod
    def _slug(text: str) -> str:
        import re

        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug[:64] or "portfolio"

    @staticmethod
    def _evidence(samples: list[tuple[str, str, str]], max_items: int = 3) -> str:
        lines = []
        for title, _path, text in samples[:max_items]:
            snippet = " ".join(text.split())[:360]
            lines.append(f"- **{title}:** {snippet}")
        return "\n".join(lines)

    def _lesson_plan(self, topic: str, course: str, samples: list[tuple[str, str, str]]) -> str:
        return f"""# Teacher Lesson Plan: {topic}

Course: {course}
Duration: 45 minutes

## Objective

Students will explain one central cause, effect, or turning point connected to
{topic} using evidence from the provided source set.

## Materials Grounding

{self._evidence(samples)}

## Lesson Flow

1. Do Now: Students respond to a short source excerpt and identify one claim it supports.
2. Mini Lesson: Teacher models how to connect evidence to a larger historical pattern.
3. Guided Practice: Pairs annotate one passage and complete a claim-evidence-reasoning frame.
4. Independent Check: Students answer one constructed-response question.
5. Exit Ticket: Students name the strongest evidence and explain why it matters.

## Teacher Moves

- Ask students to underline exact evidence before writing.
- Prompt students to distinguish cause, effect, and significance.
- Use one shared exemplar before independent writing.
"""

    def _student_handout(self, topic: str, samples: list[tuple[str, str, str]]) -> str:
        return f"""# Student Handout: {topic}

## Do Now

What is one thing you already know about {topic}? Write one sentence and one question.

## Source Notes

{self._evidence(samples, max_items=2)}

## Claim-Evidence-Reasoning Frame

- Claim:
- Evidence from the source:
- Reasoning: This evidence matters because...

## Exit Ticket

In 4-6 sentences, explain one important part of {topic}. Use at least one piece of evidence.
"""

    @staticmethod
    def _assessment(topic: str, samples: list[tuple[str, str, str]]) -> str:
        source_title = samples[0][0]
        return f"""# Assessment: {topic}

## Multiple Choice

1. Which statement best summarizes the main idea of the {source_title} material?
   A. Historical change happens without conflict.
   B. People respond to changing economic, political, or social conditions.
   C. Geography has no effect on historical decisions.
   D. Primary sources cannot support historical claims.

Answer: B

## Constructed Response

Using evidence from the sample materials, explain one cause or effect connected to {topic}.

## Rubric

- 2 points: clear claim connected to the topic
- 2 points: accurate evidence from the materials
- 2 points: reasoning explains how the evidence supports the claim
"""

    @staticmethod
    def _differentiation(topic: str, course: str) -> str:
        return f"""# Differentiation Notes: {topic}

Course: {course}

## ENL / Vocabulary

- Pre-teach five terms with examples and a visual cue.
- Let students write the claim first in home language, then translate key terms.

## Struggling Readers

- Provide sentence starters for claim, evidence, and reasoning.
- Chunk source text into short numbered sections.

## Advanced Extension

- Ask students to compare this topic with another unit and identify a pattern of change.
"""

    @staticmethod
    def _parent_note(topic: str, course: str) -> str:
        return f"""# Parent Note Draft

Subject: What we are studying in {course}

Hello,

This week we are studying {topic}. Students are practicing how to use evidence
from class materials to make clear historical claims. A helpful at-home question
is: "What evidence did you use today, and how did it support your answer?"

Thank you.
"""

    @staticmethod
    def _showcase(topic: str, course: str, source_status: str) -> str:
        return f"""# Advertising Showcase: {topic}

This sample demonstrates the Claw-ED harness:

- The Mac agent reads cleared lesson materials.
- It turns those materials into a teacher plan, student handout, assessment,
  differentiation notes, and parent communication.
- It writes every artifact to the local Mac workspace.
- Risky actions stay behind approvals.
- The iPhone companion can start this workflow remotely and resolve approvals.

Course: {course}
Source status: {source_status}

Public-facing claim: bring a folder of lesson materials; Claw-ED helps turn it
into teachable classroom outputs while keeping the teacher in control.
"""
