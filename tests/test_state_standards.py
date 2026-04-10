"""Tests for 50-state standards configuration."""

from clawed.state_standards import (
    STATE_STANDARDS_CONFIG,
    get_framework_description,
    get_standards_context_for_prompt,
    get_state_framework,
    list_states,
)


def test_all_states_present():
    """All 50 states + DC must be in the config."""
    assert len(STATE_STANDARDS_CONFIG) >= 51


def test_ny_framework():
    assert get_state_framework("NY", "social_studies") == "NY_SS"


def test_ny_math():
    assert get_state_framework("NY", "math") == "NY_NGLS"


def test_tx_uses_teks():
    assert "TEKS" in get_state_framework("TX", "math")


def test_va_uses_sol():
    assert "SOL" in get_state_framework("VA", "math")


def test_fl_uses_best():
    assert "BEST" in get_state_framework("FL", "math")


def test_ca_social_studies():
    assert get_state_framework("CA", "social_studies") == "CA_HSS"


def test_in_academic_standards():
    assert get_state_framework("IN", "science") == "IN_ALS"


def test_ccss_states():
    """States that adopted CCSS directly should return 'CCSS' for math."""
    ccss_states = [
        "AL",
        "CO",
        "CT",
        "DE",
        "HI",
        "ID",
        "IL",
        "IA",
        "KS",
        "ME",
        "MD",
        "MT",
        "NV",
        "NH",
        "ND",
        "OR",
        "RI",
        "SD",
        "VT",
        "WA",
        "WY",
    ]
    for st in ccss_states:
        assert get_state_framework(st, "math") == "CCSS", f"{st} should use CCSS for math"


def test_list_states_count():
    states = list_states()
    assert len(states) >= 51


def test_list_states_sorted():
    states = list_states()
    names = [s["name"] for s in states]
    assert names == sorted(names)


def test_list_states_structure():
    states = list_states()
    for s in states:
        assert "abbreviation" in s
        assert "name" in s
        assert len(s["abbreviation"]) == 2


def test_framework_description_known():
    desc = get_framework_description("CCSS")
    assert desc == "Common Core State Standards"


def test_framework_description_fallback():
    desc = get_framework_description("UNKNOWN_CODE")
    assert desc == "UNKNOWN_CODE"


def test_get_state_framework_invalid_state():
    assert get_state_framework("ZZ", "math") == ""


def test_get_state_framework_invalid_subject():
    assert get_state_framework("NY", "underwater_basket_weaving") == ""


def test_get_state_framework_case_insensitive():
    assert get_state_framework("ny", "Math") == "NY_NGLS"


def test_standards_context_contains_framework():
    ctx = get_standards_context_for_prompt("NY", ["math", "social_studies"], ["8", "9"])
    assert "New York" in ctx
    assert "NY_NGLS" in ctx
    assert "NY_SS" in ctx
    assert "8, 9" in ctx


def test_standards_context_contains_alignment_instruction():
    ctx = get_standards_context_for_prompt("TX", ["math"], ["6"])
    assert "align" in ctx.lower()
    assert "TEKS" in ctx


def test_standards_context_invalid_state():
    assert get_standards_context_for_prompt("ZZ", ["math"], ["5"]) == ""


def test_standards_context_empty_subjects():
    ctx = get_standards_context_for_prompt("NY", [], ["8"])
    assert ctx == ""


def test_every_state_has_all_subjects():
    """Every state entry must have math, ela, science, social_studies."""
    for abbr, cfg in STATE_STANDARDS_CONFIG.items():
        assert "math" in cfg, f"{abbr} missing math"
        assert "ela" in cfg, f"{abbr} missing ela"
        assert "science" in cfg, f"{abbr} missing science"
        assert "social_studies" in cfg, f"{abbr} missing social_studies"


def test_teacher_profile_get_standards_context():
    """TeacherProfile.get_standards_context() delegates to state_standards."""
    from clawed.models import TeacherProfile

    profile = TeacherProfile(
        state="NY",
        subjects=["math", "social_studies"],
        grade_levels=["8", "9", "10"],
    )
    ctx = profile.get_standards_context()
    assert "New York" in ctx
    assert "NY_NGLS" in ctx
    assert "NY_SS" in ctx


def test_teacher_profile_no_state():
    from clawed.models import TeacherProfile

    profile = TeacherProfile(subjects=["math"], grade_levels=["5"])
    assert profile.get_standards_context() == ""
