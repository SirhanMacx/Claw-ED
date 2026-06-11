"""Tests for the INGEST skill: style profiling, caching, persistence,
prompt injection, and the get/set profile tools."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from clawed import style_profile as sp
from clawed.agent_core.context import AgentContext
from clawed.agent_core.tools.ingest_materials import IngestMaterialsTool
from clawed.agent_core.tools.style_profile_tools import (
    GetStyleProfileTool,
    SetActiveProfileTool,
)
from clawed.models import DocType, Document

# A guided-notes style lesson in the CEO's direct/curt register.
LESSON_TEXT = """Do Now: Answer in 2-3 complete sentences. What does "cold" mean in the Cold War?

Aim: How did the Cold War divide Europe?

Directions: Read each document and answer the questions that follow.

Document 1 — excerpt adapted from Winston Churchill, "Iron Curtain" speech, 1946.

1. According to this document, what is the Iron Curtain? (2 points)

Word Bank: containment, NATO, Warsaw Pact, satellite state

Use the sentence starters below to begin your answer.

Exit Ticket: In 1-2 sentences, explain why Berlin mattered to both superpowers.

Homework: Finish the causes and effects T-chart.
"""

KEY_TEXT = """Unit 6 Quiz — Answer Key (Teacher Copy)

1. B
2. D
3. A
4. C
5. B
6. A
7. D
8. C

CRQ scoring rubric: full credit requires evidence from the document.
"""


def _docs() -> list[Document]:
    return [
        Document(title="Cold War Day 1", content=LESSON_TEXT,
                 doc_type=DocType.DOCX, source_path="/x/day1.docx"),
        Document(title="Cold War Day 2", content=LESSON_TEXT.replace("Berlin", "Korea"),
                 doc_type=DocType.DOCX, source_path="/x/day2.docx"),
        Document(title="Unit 6 Quiz KEY", content=KEY_TEXT,
                 doc_type=DocType.DOCX, source_path="/x/key.docx"),
    ]


def _context(**overrides: Any) -> AgentContext:
    defaults: dict[str, Any] = dict(
        teacher_id="t-test",
        config=None,
        teacher_profile={},
        persona=None,
        session_history=[],
        improvement_context="",
    )
    defaults.update(overrides)
    return AgentContext(**defaults)


class StubLLM:
    """Counts calls; returns canned per-file and reduce analyses."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate_json(self, prompt: str, system: str = "",
                            temperature: float = 0.4, max_tokens: int = 8192,
                            demo_hint: str = "") -> dict[str, Any]:
        self.calls += 1
        if demo_hint == "style_profile_reduce":
            return {
                "voice_description": "Your materials are direct and curt guided notes.",
                "structure_summary": "Your lessons usually open with a Do-Now.",
                "vocabulary_level": "grade_appropriate",
            }
        return {
            "tone": "direct",
            "register": "plain classroom language",
            "person": "second person (you)",
            "conventions": ["numbered document questions with point values"],
            "snippet": "Do Now: Answer in 2-3 complete sentences.",
        }


# ── Heuristics ───────────────────────────────────────────────────────


def test_detect_sections_finds_lesson_flow() -> None:
    names = [n for n, _ in sp.detect_sections(LESSON_TEXT)]
    for expected in ("Do Now", "Aim/Objective", "Directions",
                     "Document Analysis", "Exit Ticket", "Homework"):
        assert expected in names


def test_detect_question_types_and_points() -> None:
    qtypes = sp.detect_question_types(LESSON_TEXT)
    assert "short answer" in qtypes
    assert sp.detect_point_values(LESSON_TEXT) == ["2"]


def test_detect_scaffolds() -> None:
    scaffolds = sp.detect_scaffolds(LESSON_TEXT)
    assert "word banks" in scaffolds
    assert "sentence starters" in scaffolds
    assert "primary-source excerpts" in scaffolds


def test_answer_key_detection_and_letter_runs() -> None:
    assert sp.is_answer_key_doc("Unit 6 Quiz KEY", KEY_TEXT)
    letters = sp.detect_key_letters(KEY_TEXT)
    assert letters == ["B", "D", "A", "C", "B", "A", "D", "C"]
    assert sp.longest_letter_run(letters) == 1
    assert sp.longest_letter_run(["A", "A", "A", "B"]) == 3


def test_sentence_stats_short_sentences() -> None:
    avg, count = sp.sentence_stats(LESSON_TEXT)
    assert count > 3
    assert avg < 14  # curt guided-notes register


# ── Profile build (offline, no LLM) ──────────────────────────────────


def test_build_profile_offline_structure() -> None:
    profile = asyncio.run(sp.build_profile(_docs(), name="Global 10", source_path="/x"))
    assert profile.profile_id == "global-10"
    assert profile.files_analyzed == 3
    names = [s.name for s in profile.lesson_structure]
    assert names.index("Do Now") < names.index("Exit Ticket")  # position-ordered
    assert profile.answer_key_style  # separate teacher key detected
    assert "longest same-letter run = 1" in profile.mc_letter_note
    assert profile.voice_description  # heuristic fallback fills it
    assert profile.structure_summary.startswith("Your lessons usually flow")
    assert any(e.category == "do_now" for e in profile.exemplars)


def test_build_profile_with_llm_fills_voice_fields() -> None:
    llm = StubLLM()
    profile = asyncio.run(sp.build_profile(
        _docs(), name="Global 10", source_path="/x", llm=llm,
    ))
    assert profile.voice_tone == "direct"
    assert profile.voice_description == "Your materials are direct and curt guided notes."
    assert profile.structure_summary == "Your lessons usually open with a Do-Now."
    assert "numbered document questions with point values" in profile.formatting


def test_per_file_cache_makes_reingest_incremental() -> None:
    llm1 = StubLLM()
    asyncio.run(sp.build_profile(_docs(), name="P", source_path="/x", llm=llm1))
    first_calls = llm1.calls
    assert first_calls == 3 + 1  # 3 files + 1 reduce

    llm2 = StubLLM()
    asyncio.run(sp.build_profile(_docs(), name="P", source_path="/x", llm=llm2))
    assert llm2.calls == 1  # per-file analyses cached; only the reduce runs


# ── Persistence + active pointer ─────────────────────────────────────


def test_save_load_activate_deactivate_roundtrip() -> None:
    profile = asyncio.run(sp.build_profile(_docs(), name="Global 10", source_path="/x"))
    sp.save_profile(profile)
    assert sp.load_profile("global-10") is not None
    assert sp.get_active_profile() is None

    sp.set_active_profile("global-10")
    active = sp.get_active_profile()
    assert active is not None and active.name == "Global 10"

    sp.set_active_profile(None)  # the off-switch
    assert sp.get_active_profile() is None
    assert sp.load_profile("global-10") is not None  # profile kept


def test_delete_profile_clears_active_pointer() -> None:
    profile = asyncio.run(sp.build_profile(_docs(), name="Temp", source_path="/x"))
    sp.save_profile(profile)
    sp.set_active_profile(profile.profile_id)
    assert sp.delete_profile(profile.profile_id)
    assert sp.get_active_profile_id() is None
    assert not sp.delete_profile(profile.profile_id)  # already gone


# ── Prompt injection ─────────────────────────────────────────────────


def test_prompt_block_carries_the_style_facts() -> None:
    profile = asyncio.run(sp.build_profile(_docs(), name="Global 10", source_path="/x"))
    block = sp.prompt_block(profile)
    assert "ACTIVE STYLE PROFILE" in block
    assert "Do Now" in block
    assert "SEPARATE document" in block  # answer-key rule
    assert "longest same-letter run" in block


def test_active_prompt_block_empty_without_active_profile() -> None:
    assert sp.active_prompt_block() == ""


def test_agent_system_prompt_includes_active_profile() -> None:
    from clawed.agent_core.prompt import build_system_prompt

    profile = asyncio.run(sp.build_profile(_docs(), name="Global 10", source_path="/x"))
    sp.save_profile(profile)
    sp.set_active_profile(profile.profile_id)

    system = build_system_prompt(
        teacher_name="Jon",
        identity_summary="",
        improvement_context="",
        tool_names=["generate_lesson"],
        style_profile_context=sp.active_prompt_block(),
    )
    assert "ACTIVE STYLE PROFILE" in system
    assert "Global 10" in system


def test_llm_client_enriches_system_with_active_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every LLMClient.generate (lessons, assessments…) gets the profile."""
    from clawed.llm import LLMClient
    from clawed.models import AppConfig

    profile = asyncio.run(sp.build_profile(_docs(), name="Global 10", source_path="/x"))
    sp.save_profile(profile)
    sp.set_active_profile(profile.profile_id)

    client = LLMClient(AppConfig())
    enriched = client._enrich_system_prompt("Base system.", prompt="a history lesson")
    assert "ACTIVE STYLE PROFILE" in enriched
    assert enriched.startswith("Base system.")

    sp.set_active_profile(None)
    plain = client._enrich_system_prompt("Base system.", prompt="a history lesson")
    assert "ACTIVE STYLE PROFILE" not in plain


# ── Tools ────────────────────────────────────────────────────────────


def test_ingest_tool_approval_is_scoped_to_the_folder_tree() -> None:
    tool = IngestMaterialsTool()
    assert tool.risk_level == "write_local"
    assert tool.approval_scope == "per_params"
    sig1 = IngestMaterialsTool.approval_signature({"path": "~/Documents/G10"})
    sig2 = IngestMaterialsTool.approval_signature({"path": "~/Documents/G10"})
    sig3 = IngestMaterialsTool.approval_signature({"path": "~/Documents/Other"})
    assert sig1 == sig2 != sig3
    desc = IngestMaterialsTool.approval_description({"path": "~/Documents/G10"})
    assert "read-only" in desc.lower()


async def test_ingest_tool_denies_outside_home_and_secrets(tmp_path: Path) -> None:
    tool = IngestMaterialsTool()
    result = await tool.execute({"path": "/etc"}, _context())
    assert "home directory" in result.text
    result = await tool.execute({"path": "~/.ssh"}, _context())
    assert "credentials" in result.text


async def test_ingest_tool_builds_and_activates_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    materials = tmp_path / "materials"
    materials.mkdir()
    (materials / "day1.txt").write_text(LESSON_TEXT, encoding="utf-8")
    (materials / "key.txt").write_text(KEY_TEXT, encoding="utf-8")
    (materials / "junk.xyz").write_bytes(b"\x00\x01unsupported")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    tool = IngestMaterialsTool()
    result = await tool.execute(
        {"path": str(materials), "profile_name": "Test Course"}, _context(),
    )
    assert result.data.get("files_ingested") == 2
    assert result.data.get("style_profile_id") == "test-course"
    assert "Style profile" in result.text

    active = sp.get_active_profile()
    assert active is not None and active.name == "Test Course"
    assert any(s.name == "Do Now" for s in active.lesson_structure)


async def test_get_and_set_profile_tools() -> None:
    profile = await sp.build_profile(_docs(), name="Global 10", source_path="/x")
    sp.save_profile(profile)

    get_tool = GetStyleProfileTool()
    assert get_tool.risk_level == "read_only"
    listing = await get_tool.execute({}, _context())
    assert "Global 10" in listing.text
    assert "No profile is active" in listing.text

    set_tool = SetActiveProfileTool()
    on = await set_tool.execute({"profile_id": "global-10"}, _context())
    assert on.data["active"] == "global-10"
    assert sp.get_active_profile_id() == "global-10"

    shown = await get_tool.execute({"profile_id": "global-10"}, _context())
    assert "(ACTIVE)" in shown.text

    off = await set_tool.execute({"profile_id": "none"}, _context())
    assert off.data["active"] is None
    assert "default" in off.text.lower()

    missing = await set_tool.execute({"profile_id": "nope"}, _context())
    assert "No style profile" in missing.text


def test_corrupt_profile_file_is_skipped() -> None:
    sp.profiles_dir().mkdir(parents=True, exist_ok=True)
    (sp.profiles_dir() / "broken.json").write_text("{not json", encoding="utf-8")
    assert sp.load_profile("broken") is None
    assert all(p.profile_id != "broken" for p in sp.list_profiles())


def test_cache_roundtrip() -> None:
    h = sp._content_hash("hello")
    assert sp.cache_get(h) is None
    sp.cache_put(h, {"tone": "direct"})
    assert sp.cache_get(h) == {"tone": "direct"}
    # cache key is content-derived: different content, different key
    assert sp._content_hash("hello2") != h


def test_profile_json_on_disk_is_readable() -> None:
    profile = asyncio.run(sp.build_profile(_docs(), name="Global 10", source_path="/x"))
    path = sp.save_profile(profile)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["name"] == "Global 10"
    assert isinstance(raw["lesson_structure"], list)
