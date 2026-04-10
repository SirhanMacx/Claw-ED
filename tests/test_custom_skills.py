"""Tests for custom YAML skill loading and the plugin system."""

from __future__ import annotations

from pathlib import Path

import yaml

from clawed.skills.library import SkillLibrary, _parse_yaml_skill, generate_skill_template

# ── YAML parsing ─────────────────────────────────────────────────────


class TestParseYamlSkill:
    def _write_yaml(self, tmp_path: Path, filename: str, data: dict) -> Path:
        p = tmp_path / filename
        p.write_text(yaml.dump(data), encoding="utf-8")
        return p

    def test_parses_valid_yaml(self, tmp_path):
        data = {
            "subject": "ap_psychology",
            "display_name": "AP Psychology",
            "description": "Advanced Placement Psychology",
            "aliases": ["psychology", "psych", "ap psych"],
            "system_prompt": "You are an AP Psychology educator.",
            "lesson_prompt_additions": "Use case studies.",
            "assessment_style_notes": "AP-style FRQ.",
            "vocabulary_guidelines": "Key terms in bold.",
            "strategies": {
                "Case Study": "Present a case and analyze.",
                "Experiment Design": "Design a simple experiment.",
            },
        }
        path = self._write_yaml(tmp_path, "ap_psychology.yaml", data)
        skill = _parse_yaml_skill(path)

        assert skill is not None
        assert skill.subject == "ap_psychology"
        assert skill.display_name == "AP Psychology"
        assert "psychology" in skill.aliases
        assert "psych" in skill.aliases
        assert skill.system_prompt == "You are an AP Psychology educator."
        assert len(skill.example_strategies) == 2
        assert "Case Study" in skill.example_strategies

    def test_returns_none_for_missing_subject(self, tmp_path):
        data = {"display_name": "No Subject"}
        path = self._write_yaml(tmp_path, "bad.yaml", data)
        assert _parse_yaml_skill(path) is None

    def test_returns_none_for_non_dict(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        assert _parse_yaml_skill(p) is None

    def test_handles_empty_strategies(self, tmp_path):
        data = {
            "subject": "test_subj",
            "system_prompt": "Test.",
        }
        path = self._write_yaml(tmp_path, "test.yaml", data)
        skill = _parse_yaml_skill(path)
        assert skill is not None
        assert skill.example_strategies == {}

    def test_handles_string_aliases(self, tmp_path):
        data = {
            "subject": "single_alias",
            "aliases": "just-one",
        }
        path = self._write_yaml(tmp_path, "single.yaml", data)
        skill = _parse_yaml_skill(path)
        assert skill is not None
        assert "just-one" in skill.aliases

    def test_subject_is_lowercased(self, tmp_path):
        data = {"subject": "AP_Psychology"}
        path = self._write_yaml(tmp_path, "caps.yaml", data)
        skill = _parse_yaml_skill(path)
        assert skill is not None
        assert skill.subject == "ap_psychology"

    def test_defaults_for_optional_fields(self, tmp_path):
        data = {"subject": "minimal"}
        path = self._write_yaml(tmp_path, "minimal.yaml", data)
        skill = _parse_yaml_skill(path)
        assert skill is not None
        assert skill.display_name == "minimal"
        assert skill.description == ""
        assert skill.system_prompt == ""
        assert skill.lesson_prompt_additions == ""
        assert skill.assessment_style_notes == ""
        assert skill.vocabulary_guidelines == ""
        assert skill.aliases == ()
        assert skill.example_strategies == {}


# ── SkillLibrary with custom directory ───────────────────────────────


class TestSkillLibraryCustom:
    def _write_skill(self, dir_path: Path, subject: str, **kwargs) -> Path:
        data = {"subject": subject, **kwargs}
        p = dir_path / f"{subject}.yaml"
        p.write_text(yaml.dump(data), encoding="utf-8")
        return p

    def test_loads_custom_skill(self, tmp_path):
        self._write_skill(
            tmp_path,
            "ap_psychology",
            display_name="AP Psychology",
            aliases=["psych"],
            system_prompt="AP Psych educator.",
        )
        lib = SkillLibrary(custom_dir=tmp_path)
        skill = lib.get("ap_psychology")
        assert skill is not None
        assert skill.display_name == "AP Psychology"
        assert lib.is_custom("ap_psychology")

    def test_custom_accessible_by_alias(self, tmp_path):
        self._write_skill(
            tmp_path,
            "marine_bio",
            aliases=["marine biology", "ocean science"],
        )
        lib = SkillLibrary(custom_dir=tmp_path)
        assert lib.get("marine biology") is not None
        assert lib.get("ocean science") is not None
        assert lib.get("marine biology").subject == "marine_bio"

    def test_custom_overrides_builtin(self, tmp_path):
        self._write_skill(
            tmp_path,
            "math",
            display_name="Custom Math",
            system_prompt="My custom math pedagogy.",
        )
        lib = SkillLibrary(custom_dir=tmp_path)
        skill = lib.get("math")
        assert skill is not None
        assert skill.display_name == "Custom Math"
        assert skill.system_prompt == "My custom math pedagogy."
        assert lib.is_custom("math")

    def test_builtin_not_marked_custom(self, tmp_path):
        # Empty custom dir
        lib = SkillLibrary(custom_dir=tmp_path)
        assert not lib.is_custom("math")
        assert not lib.is_custom("science")

    def test_custom_skill_in_list(self, tmp_path):
        self._write_skill(
            tmp_path,
            "ap_psychology",
            display_name="AP Psychology",
        )
        lib = SkillLibrary(custom_dir=tmp_path)
        subjects = lib.subjects()
        assert "ap_psychology" in subjects

    def test_custom_skill_count(self, tmp_path):
        self._write_skill(tmp_path, "custom_a")
        self._write_skill(tmp_path, "custom_b")
        lib = SkillLibrary(custom_dir=tmp_path)
        # 11 built-in + 2 custom
        assert len(lib) == 13

    def test_empty_custom_dir_is_fine(self, tmp_path):
        lib = SkillLibrary(custom_dir=tmp_path)
        assert len(lib) == 11  # only built-in skills

    def test_nonexistent_custom_dir_is_fine(self, tmp_path):
        fake_dir = tmp_path / "does_not_exist"
        lib = SkillLibrary(custom_dir=fake_dir)
        assert len(lib) == 11

    def test_bad_yaml_file_is_skipped(self, tmp_path):
        # Write invalid YAML
        (tmp_path / "bad.yaml").write_text("{{{{not valid yaml", encoding="utf-8")
        lib = SkillLibrary(custom_dir=tmp_path)
        # Should still load all built-in skills
        assert len(lib) == 11


# ── Template generation ──────────────────────────────────────────────


class TestGenerateSkillTemplate:
    def test_generates_file(self, tmp_path):
        path = generate_skill_template("AP Psychology", output_dir=tmp_path)
        assert path.exists()
        assert path.name == "ap_psychology.yaml"

    def test_file_is_valid_yaml(self, tmp_path):
        path = generate_skill_template("my_subject", output_dir=tmp_path)
        data = yaml.safe_load(path.read_text())
        assert data["subject"] == "my_subject"
        assert "display_name" in data
        assert "strategies" in data
        assert "aliases" in data

    def test_template_loadable_as_skill(self, tmp_path):
        path = generate_skill_template("test_skill", output_dir=tmp_path)
        skill = _parse_yaml_skill(path)
        assert skill is not None
        assert skill.subject == "test_skill"
        assert len(skill.example_strategies) >= 2

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        path = generate_skill_template("deep", output_dir=nested)
        assert path.exists()

    def test_loaded_by_library(self, tmp_path):
        generate_skill_template("custom_geo", output_dir=tmp_path)
        lib = SkillLibrary(custom_dir=tmp_path)
        assert "custom_geo" in lib
        assert lib.is_custom("custom_geo")
