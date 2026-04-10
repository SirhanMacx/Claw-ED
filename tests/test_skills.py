"""Tests for the subject skill library."""

import pytest

from clawed.skills import SkillLibrary, SubjectSkill

# ── SubjectSkill dataclass ─────────────────────────────────────────


class TestSubjectSkill:
    def test_create_skill(self):
        skill = SubjectSkill(
            subject="test",
            display_name="Test Subject",
            description="A test skill.",
            system_prompt="You are a test teacher.",
            lesson_prompt_additions="Test lesson additions.",
            assessment_style_notes="Test assessment notes.",
            vocabulary_guidelines="Test vocabulary guidelines.",
        )
        assert skill.subject == "test"
        assert skill.display_name == "Test Subject"
        assert skill.example_strategies == {}
        assert skill.aliases == ()

    def test_skill_is_frozen(self):
        skill = SubjectSkill(
            subject="test",
            display_name="Test",
            description="Test",
            system_prompt="",
            lesson_prompt_additions="",
            assessment_style_notes="",
            vocabulary_guidelines="",
        )
        with pytest.raises(AttributeError):
            skill.subject = "changed"

    def test_to_system_context(self):
        skill = SubjectSkill(
            subject="test",
            display_name="Test Subject",
            description="Desc",
            system_prompt="System prompt here.",
            lesson_prompt_additions="Lesson additions here.",
            assessment_style_notes="Assessment notes here.",
            vocabulary_guidelines="Vocabulary guidelines here.",
            example_strategies={"Strategy A": "Description of A"},
        )
        ctx = skill.to_system_context()
        assert "## Subject Pedagogy: Test Subject" in ctx
        assert "System prompt here." in ctx
        assert "Lesson additions here." in ctx
        assert "Assessment notes here." in ctx
        assert "Vocabulary guidelines here." in ctx
        assert "Strategy A" in ctx
        assert "Description of A" in ctx

    def test_to_lesson_injection(self):
        skill = SubjectSkill(
            subject="test",
            display_name="Test Subject",
            description="Desc",
            system_prompt="System prompt.",
            lesson_prompt_additions="Lesson guidance.",
            assessment_style_notes="Assessment approach.",
            vocabulary_guidelines="Vocab rules.",
        )
        injection = skill.to_lesson_injection()
        assert "Test Subject" in injection
        assert "Lesson guidance." in injection
        assert "Assessment approach." in injection
        assert "Vocab rules." in injection


# ── SkillLibrary ───────────────────────────────────────────────────


class TestSkillLibrary:
    @pytest.fixture
    def library(self, tmp_path):
        # Use an empty custom_dir so user-installed YAML skills don't interfere
        return SkillLibrary(custom_dir=tmp_path)

    def test_loads_all_skills(self, library):
        assert len(library) >= 11

    def test_expected_subjects_present(self, library):
        expected = {
            "ela",
            "history",
            "math",
            "science",
            "social_studies",
            "foreign_language",
            "art",
            "music",
            "physical_education",
            "computer_science",
            "special_education",
        }
        assert set(library.subjects()) == expected

    def test_get_by_canonical_name(self, library):
        skill = library.get("math")
        assert skill is not None
        assert skill.subject == "math"
        assert skill.display_name == "Mathematics"

    def test_get_by_alias(self, library):
        # "biology" should resolve to "science"
        skill = library.get("biology")
        assert skill is not None
        assert skill.subject == "science"

    def test_get_case_insensitive(self, library):
        assert library.get("MATH") is not None
        assert library.get("Math") is not None
        assert library.get("  math  ") is not None

    def test_get_unknown_returns_none(self, library):
        assert library.get("underwater basket weaving") is None

    def test_contains(self, library):
        assert "math" in library
        assert "algebra" in library  # alias
        assert "zzz" not in library

    def test_list_skills_sorted_by_display_name(self, library):
        skills = library.list_skills()
        names = [s.display_name for s in skills]
        assert names == sorted(names)

    def test_iterate(self, library):
        subjects = [s.subject for s in library]
        assert len(subjects) >= 11

    def test_inject_system_context_known(self, library):
        ctx = library.inject_system_context("science")
        assert "Subject Pedagogy: Science" in ctx
        assert "NGSS" in ctx

    def test_inject_system_context_unknown(self, library):
        assert library.inject_system_context("xyz") == ""

    def test_inject_lesson_context_known(self, library):
        ctx = library.inject_lesson_context("ela")
        assert "English Language Arts" in ctx
        assert "close reading" in ctx.lower()

    def test_inject_lesson_context_unknown(self, library):
        assert library.inject_lesson_context("xyz") == ""


# ── Individual skill modules ──────────────────────────────────────


class TestSocialStudiesSkill:
    def test_loads(self):
        from clawed.skills.social_studies import skill

        assert skill.subject == "social_studies"
        assert "DBQ" in skill.lesson_prompt_additions
        assert "MAIN" in skill.lesson_prompt_additions
        assert "Socratic" in skill.lesson_prompt_additions
        assert len(skill.example_strategies) >= 3

    def test_aliases(self):
        from clawed.skills.social_studies import skill

        assert "civics" in skill.aliases
        assert "government" in skill.aliases


class TestMathSkill:
    def test_loads(self):
        from clawed.skills.math import skill

        assert skill.subject == "math"
        assert "worked example" in skill.lesson_prompt_additions.lower()
        assert "scaffold" in skill.lesson_prompt_additions.lower()
        lpa = skill.lesson_prompt_additions.lower()
        assert "multiple representation" in lpa or "representations" in lpa
        assert len(skill.example_strategies) >= 3

    def test_aliases(self):
        from clawed.skills.math import skill

        assert "algebra" in skill.aliases
        assert "geometry" in skill.aliases
        assert "calculus" in skill.aliases


class TestScienceSkill:
    def test_loads(self):
        from clawed.skills.science import skill

        assert skill.subject == "science"
        assert "NGSS" in skill.system_prompt
        assert "CER" in skill.lesson_prompt_additions
        assert "5E" in skill.lesson_prompt_additions or "5e" in skill.lesson_prompt_additions.lower()
        assert len(skill.example_strategies) >= 3

    def test_aliases(self):
        from clawed.skills.science import skill

        assert "biology" in skill.aliases
        assert "chemistry" in skill.aliases
        assert "physics" in skill.aliases


class TestELASkill:
    def test_loads(self):
        from clawed.skills.ela import skill

        assert skill.subject == "ela"
        assert "close reading" in skill.lesson_prompt_additions.lower()
        lpa = skill.lesson_prompt_additions.lower()
        assert "textual evidence" in lpa or "text" in lpa
        assert "writing workshop" in skill.lesson_prompt_additions.lower()
        assert len(skill.example_strategies) >= 3

    def test_aliases(self):
        from clawed.skills.ela import skill

        assert "english" in skill.aliases
        assert "reading" in skill.aliases
        assert "writing" in skill.aliases


class TestHistorySkill:
    def test_loads(self):
        from clawed.skills.history import skill

        assert skill.subject == "history"
        assert "causation" in skill.lesson_prompt_additions.lower()
        assert "continuity" in skill.lesson_prompt_additions.lower()
        assert "change" in skill.lesson_prompt_additions.lower()
        assert "sourcing" in skill.lesson_prompt_additions.lower()
        assert len(skill.example_strategies) >= 3

    def test_aliases(self):
        from clawed.skills.history import skill

        assert "us history" in skill.aliases
        assert "world history" in skill.aliases
        assert "apush" in skill.aliases


# ── Alias coverage ─────────────────────────────────────────────────


class TestAliasCoverage:
    """Ensure common subject terms resolve to the right skill."""

    @pytest.fixture
    def library(self):
        return SkillLibrary()

    @pytest.mark.parametrize(
        "alias,expected_subject",
        [
            ("mathematics", "math"),
            ("algebra", "math"),
            ("geometry", "math"),
            ("calculus", "math"),
            ("statistics", "math"),
            ("biology", "science"),
            ("chemistry", "science"),
            ("physics", "science"),
            ("earth science", "science"),
            ("english", "ela"),
            ("reading", "ela"),
            ("writing", "ela"),
            ("literature", "ela"),
            ("language arts", "ela"),
            ("social studies", "social_studies"),
            ("civics", "social_studies"),
            ("government", "social_studies"),
            ("geography", "social_studies"),
            ("economics", "social_studies"),
            ("us history", "history"),
            ("world history", "history"),
            ("apush", "history"),
            ("american history", "history"),
            # New skill aliases
            ("spanish", "foreign_language"),
            ("french", "foreign_language"),
            ("mandarin", "foreign_language"),
            ("world languages", "foreign_language"),
            ("latin", "foreign_language"),
            ("visual arts", "art"),
            ("studio art", "art"),
            ("drawing", "art"),
            ("painting", "art"),
            ("band", "music"),
            ("orchestra", "music"),
            ("chorus", "music"),
            ("choir", "music"),
            ("pe", "physical_education"),
            ("fitness", "physical_education"),
            ("health", "physical_education"),
            ("gym", "physical_education"),
            ("programming", "computer_science"),
            ("coding", "computer_science"),
            ("ap cs", "computer_science"),
            ("robotics", "computer_science"),
            ("sped", "special_education"),
            ("iep", "special_education"),
            ("inclusion", "special_education"),
            ("udl", "special_education"),
        ],
    )
    def test_alias_resolves(self, library, alias, expected_subject):
        skill = library.get(alias)
        assert skill is not None, f"Alias '{alias}' did not resolve"
        assert skill.subject == expected_subject, f"'{alias}' resolved to {skill.subject}, expected {expected_subject}"


# ── New skill module tests ──────────────────────────────────────


class TestForeignLanguageSkill:
    def test_loads(self):
        from clawed.skills.foreign_language import skill

        assert skill.subject == "foreign_language"
        assert "communicative" in skill.lesson_prompt_additions.lower()
        assert "actfl" in skill.system_prompt.upper() or "ACTFL" in skill.system_prompt
        assert len(skill.example_strategies) >= 4

    def test_aliases(self):
        from clawed.skills.foreign_language import skill

        assert "spanish" in skill.aliases
        assert "french" in skill.aliases
        assert "mandarin" in skill.aliases


class TestArtSkill:
    def test_loads(self):
        from clawed.skills.art import skill

        assert skill.subject == "art"
        assert "studio" in skill.lesson_prompt_additions.lower()
        assert "national core arts" in skill.system_prompt.lower()
        assert len(skill.example_strategies) >= 4

    def test_aliases(self):
        from clawed.skills.art import skill

        assert "visual arts" in skill.aliases
        assert "drawing" in skill.aliases
        assert "painting" in skill.aliases


class TestMusicSkill:
    def test_loads(self):
        from clawed.skills.music import skill

        assert skill.subject == "music"
        assert "perform" in skill.lesson_prompt_additions.lower()
        assert len(skill.example_strategies) >= 4

    def test_aliases(self):
        from clawed.skills.music import skill

        assert "band" in skill.aliases
        assert "orchestra" in skill.aliases
        assert "chorus" in skill.aliases


class TestPhysicalEducationSkill:
    def test_loads(self):
        from clawed.skills.physical_education import skill

        assert skill.subject == "physical_education"
        assert "shape america" in skill.system_prompt.lower()
        assert "fitt" in skill.lesson_prompt_additions.upper() or "FITT" in skill.lesson_prompt_additions
        assert len(skill.example_strategies) >= 4

    def test_aliases(self):
        from clawed.skills.physical_education import skill

        assert "pe" in skill.aliases
        assert "fitness" in skill.aliases
        assert "health" in skill.aliases


class TestComputerScienceSkill:
    def test_loads(self):
        from clawed.skills.computer_science import skill

        assert skill.subject == "computer_science"
        assert "computational thinking" in skill.system_prompt.lower()
        assert "csta" in skill.system_prompt.upper() or "CSTA" in skill.system_prompt
        assert len(skill.example_strategies) >= 4

    def test_aliases(self):
        from clawed.skills.computer_science import skill

        assert "programming" in skill.aliases
        assert "coding" in skill.aliases
        assert "robotics" in skill.aliases


class TestSpecialEducationSkill:
    def test_loads(self):
        from clawed.skills.special_education import skill

        assert skill.subject == "special_education"
        assert "udl" in skill.system_prompt.lower() or "UDL" in skill.system_prompt
        assert "iep" in skill.lesson_prompt_additions.lower() or "IEP" in skill.lesson_prompt_additions
        assert len(skill.example_strategies) >= 4

    def test_aliases(self):
        from clawed.skills.special_education import skill

        assert "sped" in skill.aliases
        assert "iep" in skill.aliases
        assert "inclusion" in skill.aliases
