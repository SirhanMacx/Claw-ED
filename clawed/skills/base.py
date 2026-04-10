"""Base class for subject skills."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubjectSkill:
    """A domain-specific pedagogy pack that shapes LLM generation.

    Each skill carries prompt fragments, assessment guidance, vocabulary rules,
    and instructional strategies tuned to a specific academic subject.
    """

    subject: str
    display_name: str
    description: str

    # Core prompt fragments
    system_prompt: str
    lesson_prompt_additions: str
    assessment_style_notes: str
    vocabulary_guidelines: str

    # Instructional strategies (name → description)
    example_strategies: dict[str, str] = field(default_factory=dict)

    # Aliases that resolve to this skill (e.g., "us history" → "history")
    aliases: tuple[str, ...] = ()

    def to_system_context(self) -> str:
        """Serialize skill into a block suitable for LLM system prompt injection."""
        strategies = "\n".join(f"  - {name}: {desc}" for name, desc in self.example_strategies.items())
        return (
            f"## Subject Pedagogy: {self.display_name}\n\n"
            f"{self.system_prompt}\n\n"
            f"### Lesson Design Guidance\n{self.lesson_prompt_additions}\n\n"
            f"### Assessment Style\n{self.assessment_style_notes}\n\n"
            f"### Vocabulary Guidelines\n{self.vocabulary_guidelines}\n\n"
            f"### Recommended Strategies\n{strategies}\n"
        )

    def to_lesson_injection(self) -> str:
        """Compact injection for lesson plan prompts."""
        return (
            f"Subject-specific guidance ({self.display_name}):\n"
            f"{self.lesson_prompt_additions}\n"
            f"Assessment approach: {self.assessment_style_notes}\n"
            f"Vocabulary: {self.vocabulary_guidelines}\n"
        )
