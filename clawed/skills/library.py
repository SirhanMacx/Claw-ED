"""SkillLibrary — loads and resolves subject skills for prompt injection."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Iterator

from clawed.skills.base import SubjectSkill

logger = logging.getLogger(__name__)


# Default location for user-defined custom YAML skills
def _custom_skills_dir():
    from clawed.paths import custom_skills_dir

    return custom_skills_dir()


CUSTOM_SKILLS_DIR = None  # resolved lazily via _custom_skills_dir()


class SkillLibrary:
    """Registry of subject-specific pedagogy skills.

    Discovers all skill modules in the ``clawed.skills`` package at
    instantiation time and indexes them by canonical subject name and aliases.
    Then scans ``~/.eduagent/skills/`` for user-defined YAML skill files.
    Custom skills override built-in skills with the same subject name.
    """

    def __init__(self, custom_dir: Path | None = None) -> None:
        self._skills: dict[str, SubjectSkill] = {}
        self._alias_map: dict[str, str] = {}
        self._custom_subjects: set[str] = set()
        self._custom_dir = custom_dir if custom_dir is not None else _custom_skills_dir()
        self._load_all()
        self._load_custom_skills()

    # ── Discovery ──────────────────────────────────────────────────────

    def _load_all(self) -> None:
        """Walk ``eduagent.skills`` and import every module that exposes a ``skill`` attribute."""
        package_dir = Path(__file__).parent
        for info in pkgutil.iter_modules([str(package_dir)]):
            if info.name in ("base", "library", "__init__"):
                continue
            mod = importlib.import_module(f"clawed.skills.{info.name}")
            skill: SubjectSkill | None = getattr(mod, "skill", None)
            if skill is None:
                continue
            self._skills[skill.subject] = skill
            # Register aliases
            for alias in skill.aliases:
                self._alias_map[alias.lower()] = skill.subject

    def _load_custom_skills(self) -> None:
        """Scan ``~/.eduagent/skills/*.yaml`` for user-defined skill definitions.

        Custom skills override built-in skills with the same subject name,
        allowing teachers to customize pedagogy packs.
        """
        if not self._custom_dir.is_dir():
            return

        try:
            import yaml  # noqa: F401 — checked here for availability, used in _parse_yaml_skill
        except ImportError:
            logger.warning(
                "pyyaml is not installed — custom YAML skills will not be loaded. Install with: pip install pyyaml"
            )
            return

        for yaml_path in sorted(self._custom_dir.glob("*.yaml")):
            try:
                skill = _parse_yaml_skill(yaml_path)
                if skill is None:
                    continue
                # Override any existing skill with the same subject name
                self._skills[skill.subject] = skill
                self._custom_subjects.add(skill.subject)
                # Register aliases (overwrite any conflicting aliases)
                for alias in skill.aliases:
                    self._alias_map[alias.lower()] = skill.subject
                logger.debug("Loaded custom skill: %s from %s", skill.subject, yaml_path)
            except Exception as exc:
                logger.warning("Failed to load custom skill from %s: %s", yaml_path, exc)

    # ── Lookup ─────────────────────────────────────────────────────────

    def get(self, subject: str) -> SubjectSkill | None:
        """Resolve a subject name (or alias) to a SubjectSkill, or ``None``."""
        key = subject.lower().strip()
        # Direct match
        if key in self._skills:
            return self._skills[key]
        # Alias match
        canonical = self._alias_map.get(key)
        if canonical:
            return self._skills[canonical]
        return None

    def list_skills(self) -> list[SubjectSkill]:
        """Return all registered skills sorted by display name."""
        return sorted(self._skills.values(), key=lambda s: s.display_name)

    def subjects(self) -> list[str]:
        """Return canonical subject keys."""
        return sorted(self._skills.keys())

    def is_custom(self, subject: str) -> bool:
        """Return True if the skill was loaded from a user YAML file."""
        return subject in self._custom_subjects

    def __iter__(self) -> Iterator[SubjectSkill]:
        return iter(self._skills.values())

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, subject: str) -> bool:
        return self.get(subject) is not None

    # ── Prompt injection helpers ───────────────────────────────────────

    def inject_system_context(self, subject: str) -> str:
        """Return the full system context block for *subject*, or empty string."""
        skill = self.get(subject)
        return skill.to_system_context() if skill else ""

    def inject_lesson_context(self, subject: str) -> str:
        """Return the compact lesson injection for *subject*, or empty string."""
        skill = self.get(subject)
        return skill.to_lesson_injection() if skill else ""


def _parse_yaml_skill(path: Path) -> SubjectSkill | None:
    """Parse a YAML file into a SubjectSkill instance.

    Returns None if the file is missing required fields.
    """
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return None

    subject = data.get("subject")
    if not subject:
        return None

    strategies_raw = data.get("strategies") or {}
    if not isinstance(strategies_raw, dict):
        strategies_raw = {}

    aliases_raw = data.get("aliases") or []
    if isinstance(aliases_raw, str):
        aliases_raw = [aliases_raw]

    return SubjectSkill(
        subject=str(subject).lower().strip(),
        display_name=data.get("display_name", subject),
        description=data.get("description", ""),
        system_prompt=data.get("system_prompt", ""),
        lesson_prompt_additions=data.get("lesson_prompt_additions", ""),
        assessment_style_notes=data.get("assessment_style_notes", ""),
        vocabulary_guidelines=data.get("vocabulary_guidelines", ""),
        example_strategies={str(k): str(v) for k, v in strategies_raw.items()},
        aliases=tuple(str(a) for a in aliases_raw),
    )


def generate_skill_template(subject: str, output_dir: Path | None = None) -> Path:
    """Generate a template YAML skill file in the custom skills directory.

    Returns the path to the created file.
    """
    target_dir = output_dir if output_dir is not None else _custom_skills_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{subject.lower().replace(' ', '_')}.yaml"
    filepath = target_dir / filename

    template = f"""\
subject: {subject.lower().replace(" ", "_")}
display_name: "{subject.title()}"
description: "Custom pedagogy skill for {subject.title()}"
aliases:
  - {subject.lower()}
system_prompt: |
  You are an expert {subject.title()} educator. Design instruction that
  develops deep understanding through evidence-based practices.
  Customize this prompt with subject-specific pedagogy.
lesson_prompt_additions: |
  Structure lessons using research-based instructional strategies.
  Add your subject-specific lesson design guidance here.
assessment_style_notes: |
  Design assessments that measure deep understanding.
  Add your subject-specific assessment guidance here.
vocabulary_guidelines: |
  Teach key vocabulary explicitly with multiple exposures.
  Add your subject-specific vocabulary guidance here.
strategies:
  Example Strategy 1: "Describe an instructional strategy specific to {subject.title()}."
  Example Strategy 2: "Describe another strategy."
"""
    filepath.write_text(template, encoding="utf-8")
    return filepath
