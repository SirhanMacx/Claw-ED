"""50-state standards configuration for Claw-ED.

Maps every US state + DC to its adopted standards frameworks for
math, ELA, science, and social studies. Used to auto-tailor all
generated content to the teacher's state.
"""

from __future__ import annotations

STATE_STANDARDS_CONFIG: dict[str, dict[str, str]] = {
    "AL": {"name": "Alabama", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "AK": {"name": "Alaska", "math": "AK_MATH", "ela": "AK_ELA", "science": "AK_SCIENCE", "social_studies": "C3"},
    "AZ": {"name": "Arizona", "math": "CCSS_AZ", "ela": "CCSS_AZ", "science": "NGSS", "social_studies": "C3"},
    "AR": {"name": "Arkansas", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "CA": {"name": "California", "math": "CCSS_CA", "ela": "CCSS_CA", "science": "NGSS", "social_studies": "CA_HSS"},
    "CO": {"name": "Colorado", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "CT": {"name": "Connecticut", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "DE": {"name": "Delaware", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "DC": {"name": "District of Columbia", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "FL": {"name": "Florida", "math": "FL_BEST", "ela": "FL_BEST", "science": "FL_NGSSS", "social_studies": "FL_SS"},
    "GA": {"name": "Georgia", "math": "GA_MGSE", "ela": "GA_ELA", "science": "GA_SCIENCE", "social_studies": "C3"},
    "HI": {"name": "Hawaii", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "ID": {"name": "Idaho", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "IL": {"name": "Illinois", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "IN": {"name": "Indiana", "math": "IN_ALS", "ela": "IN_ALS", "science": "IN_ALS", "social_studies": "C3"},
    "IA": {"name": "Iowa", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "KS": {"name": "Kansas", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "KY": {"name": "Kentucky", "math": "KY_ACAS", "ela": "KY_ACAS", "science": "NGSS", "social_studies": "KY_SS"},
    "LA": {"name": "Louisiana", "math": "CCSS_LA", "ela": "CCSS_LA", "science": "NGSS", "social_studies": "C3"},
    "ME": {"name": "Maine", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "MD": {"name": "Maryland", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "MA": {
        "name": "Massachusetts",
        "math": "MA_CCSS",
        "ela": "MA_CCSS",
        "science": "MA_SCIENCE",
        "social_studies": "MA_HSS",
    },
    "MI": {"name": "Michigan", "math": "CCSS", "ela": "CCSS", "science": "MI_SCIENCE", "social_studies": "C3"},
    "MN": {"name": "Minnesota", "math": "MN_MATH", "ela": "CCSS", "science": "NGSS", "social_studies": "MN_SS"},
    "MS": {"name": "Mississippi", "math": "CCSS_MS", "ela": "CCSS_MS", "science": "NGSS", "social_studies": "C3"},
    "MO": {"name": "Missouri", "math": "MO_LEARN", "ela": "MO_LEARN", "science": "MO_SCIENCE", "social_studies": "C3"},
    "MT": {"name": "Montana", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "NE": {"name": "Nebraska", "math": "NE_MATH", "ela": "NE_ELA", "science": "NGSS", "social_studies": "NE_SS"},
    "NV": {"name": "Nevada", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "NH": {"name": "New Hampshire", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "NJ": {"name": "New Jersey", "math": "CCSS_NJ", "ela": "CCSS_NJ", "science": "NGSS", "social_studies": "NJ_SS"},
    "NM": {"name": "New Mexico", "math": "CCSS_NM", "ela": "CCSS_NM", "science": "NGSS", "social_studies": "C3"},
    "NY": {"name": "New York", "math": "NY_NGLS", "ela": "NY_NGLS", "science": "NGSS", "social_studies": "NY_SS"},
    "NC": {
        "name": "North Carolina",
        "math": "CCSS_NC",
        "ela": "CCSS_NC",
        "science": "NC_SCIENCE",
        "social_studies": "C3",
    },
    "ND": {"name": "North Dakota", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "OH": {"name": "Ohio", "math": "OH_MATH", "ela": "OH_ELA", "science": "OH_SCIENCE", "social_studies": "OH_SS"},
    "OK": {"name": "Oklahoma", "math": "OK_MATH", "ela": "OK_ELA", "science": "OK_SCIENCE", "social_studies": "OK_SS"},
    "OR": {"name": "Oregon", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "PA": {
        "name": "Pennsylvania",
        "math": "PA_CCSS",
        "ela": "PA_CCSS",
        "science": "PA_SCIENCE",
        "social_studies": "PA_SS",
    },
    "RI": {"name": "Rhode Island", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "SC": {
        "name": "South Carolina",
        "math": "SC_CCRS",
        "ela": "SC_CCRS",
        "science": "SC_SCIENCE",
        "social_studies": "SC_SS",
    },
    "SD": {"name": "South Dakota", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "TN": {"name": "Tennessee", "math": "TN_MATH", "ela": "TN_ELA", "science": "TN_SCIENCE", "social_studies": "C3"},
    "TX": {
        "name": "Texas",
        "math": "TX_TEKS",
        "ela": "TX_TEKS_ELA",
        "science": "TX_TEKS_SCI",
        "social_studies": "TX_TEKS_SS",
    },
    "UT": {"name": "Utah", "math": "CCSS_UT", "ela": "CCSS_UT", "science": "NGSS", "social_studies": "UT_SS"},
    "VT": {"name": "Vermont", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "VA": {
        "name": "Virginia",
        "math": "VA_SOL",
        "ela": "VA_SOL",
        "science": "VA_SOL_SCI",
        "social_studies": "VA_SOL_SS",
    },
    "WA": {"name": "Washington", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
    "WV": {"name": "West Virginia", "math": "WV_CSO", "ela": "WV_CSO", "science": "NGSS", "social_studies": "C3"},
    "WI": {"name": "Wisconsin", "math": "CCSS", "ela": "CCSS", "science": "WI_SCIENCE", "social_studies": "WI_SS"},
    "WY": {"name": "Wyoming", "math": "CCSS", "ela": "CCSS", "science": "NGSS", "social_studies": "C3"},
}

FRAMEWORK_DESCRIPTIONS: dict[str, str] = {
    # National / shared frameworks
    "CCSS": "Common Core State Standards",
    "NGSS": "Next Generation Science Standards",
    "C3": "C3 Framework for Social Studies",
    # New York
    "NY_NGLS": "New York Next Generation Learning Standards",
    "NY_SS": "New York K-12 Social Studies Framework",
    # Texas
    "TX_TEKS": "Texas Essential Knowledge and Skills (TEKS)",
    "TX_TEKS_ELA": "Texas TEKS - English Language Arts",
    "TX_TEKS_SCI": "Texas TEKS - Science",
    "TX_TEKS_SS": "Texas TEKS - Social Studies",
    # Virginia
    "VA_SOL": "Virginia Standards of Learning (SOL)",
    "VA_SOL_SCI": "Virginia SOL - Science",
    "VA_SOL_SS": "Virginia SOL - Social Studies",
    # Florida
    "FL_BEST": "Florida BEST Standards",
    "FL_NGSSS": "Florida Next Generation Sunshine State Standards (Science)",
    "FL_SS": "Florida Social Studies Standards",
    # Indiana
    "IN_ALS": "Indiana Academic Standards",
    # Massachusetts
    "MA_CCSS": "Massachusetts Curriculum Frameworks (CCSS-aligned)",
    "MA_SCIENCE": "Massachusetts Science and Technology/Engineering Standards",
    "MA_HSS": "Massachusetts History and Social Science Curriculum Framework",
    # California
    "CA_HSS": "California History-Social Science Framework",
    "CCSS_CA": "California Common Core State Standards",
    # Georgia
    "GA_MGSE": "Georgia Mathematics Standards of Excellence",
    "GA_ELA": "Georgia English Language Arts Standards of Excellence",
    "GA_SCIENCE": "Georgia Science Standards of Excellence",
    # Ohio
    "OH_MATH": "Ohio's Learning Standards - Mathematics",
    "OH_ELA": "Ohio's Learning Standards - English Language Arts",
    "OH_SCIENCE": "Ohio's Learning Standards - Science",
    "OH_SS": "Ohio Social Studies Learning Standards",
    # Pennsylvania
    "PA_CCSS": "Pennsylvania Core Standards (CCSS-aligned)",
    "PA_SCIENCE": "Pennsylvania Academic Standards - Science",
    "PA_SS": "Pennsylvania Academic Standards - Social Studies",
    # New Jersey
    "CCSS_NJ": "New Jersey Student Learning Standards (CCSS-aligned)",
    "NJ_SS": "New Jersey Student Learning Standards - Social Studies",
    # Kentucky
    "KY_ACAS": "Kentucky Academic Standards",
    "KY_SS": "Kentucky Academic Standards - Social Studies",
    # Tennessee
    "TN_MATH": "Tennessee Academic Standards - Mathematics",
    "TN_ELA": "Tennessee Academic Standards - English Language Arts",
    "TN_SCIENCE": "Tennessee Academic Standards - Science",
    # Oklahoma
    "OK_MATH": "Oklahoma Academic Standards - Mathematics",
    "OK_ELA": "Oklahoma Academic Standards - English Language Arts",
    "OK_SCIENCE": "Oklahoma Academic Standards - Science",
    "OK_SS": "Oklahoma Academic Standards - Social Studies",
    # South Carolina
    "SC_CCRS": "South Carolina College- and Career-Ready Standards",
    "SC_SCIENCE": "South Carolina Academic Standards - Science",
    "SC_SS": "South Carolina Social Studies Academic Standards",
    # North Carolina
    "CCSS_NC": "North Carolina Standard Course of Study (CCSS-aligned)",
    "NC_SCIENCE": "North Carolina Essential Standards - Science",
    # Missouri
    "MO_LEARN": "Missouri Learning Standards",
    "MO_SCIENCE": "Missouri Learning Standards - Science",
    # Minnesota
    "MN_MATH": "Minnesota K-12 Academic Standards - Mathematics",
    "MN_SS": "Minnesota K-12 Academic Standards - Social Studies",
    # Nebraska
    "NE_MATH": "Nebraska College and Career Ready Standards - Math",
    "NE_ELA": "Nebraska College and Career Ready Standards - ELA",
    "NE_SS": "Nebraska Social Studies Standards",
    # Michigan
    "MI_SCIENCE": "Michigan Science Standards",
    # Wisconsin
    "WI_SCIENCE": "Wisconsin Standards for Science",
    "WI_SS": "Wisconsin Standards for Social Studies",
    # Alaska
    "AK_MATH": "Alaska Mathematics Standards",
    "AK_ELA": "Alaska English Language Arts Standards",
    "AK_SCIENCE": "Alaska Science Standards",
    # Arizona / Louisiana / Mississippi / New Mexico / Utah / West Virginia (CCSS-aligned variants)
    "CCSS_AZ": "Arizona's College and Career Ready Standards (CCSS-aligned)",
    "CCSS_LA": "Louisiana Student Standards (CCSS-aligned)",
    "CCSS_MS": "Mississippi College- and Career-Readiness Standards (CCSS-aligned)",
    "CCSS_NM": "New Mexico Common Core State Standards",
    "CCSS_UT": "Utah Core Standards (CCSS-aligned)",
    "WV_CSO": "West Virginia College- and Career-Readiness Standards",
    # Utah
    "UT_SS": "Utah Social Studies Standards",
}

# Subjects recognized by the standards config
SUBJECTS = ("math", "ela", "science", "social_studies")


def get_state_framework(state: str, subject: str) -> str:
    """Return framework code for a state+subject combination.

    Args:
        state: Two-letter state abbreviation (e.g. "NY", "TX").
        subject: One of "math", "ela", "science", "social_studies".

    Returns:
        Framework code string, or empty string if not found.
    """
    state = state.upper().strip()
    subject = subject.lower().strip().replace(" ", "_")
    cfg = STATE_STANDARDS_CONFIG.get(state)
    if cfg is None:
        return ""
    return cfg.get(subject, "")


def get_framework_description(framework_code: str) -> str:
    """Return human-readable framework name.

    Falls back to the code itself if no description is registered.
    """
    return FRAMEWORK_DESCRIPTIONS.get(framework_code, framework_code)


def list_states() -> list[dict[str, str]]:
    """Return sorted list of all states/territories.

    Each entry: {"abbreviation": "NY", "name": "New York"}.
    Sorted alphabetically by full name.
    """
    return sorted(
        [{"abbreviation": abbr, "name": cfg["name"]} for abbr, cfg in STATE_STANDARDS_CONFIG.items()],
        key=lambda s: s["name"],
    )


def get_standards_context_for_prompt(
    state: str,
    subjects: list[str],
    grades: list[str],
) -> str:
    """Generate a standards context string to inject into LLM prompts.

    Produces a multi-line block describing which frameworks apply for the
    teacher's state, subjects, and grade levels so the LLM can align
    generated content accordingly.
    """
    state = state.upper().strip()
    cfg = STATE_STANDARDS_CONFIG.get(state)
    if cfg is None:
        return ""

    lines: list[str] = []
    state_name = cfg["name"]

    for subj in subjects:
        subj_key = subj.lower().strip().replace(" ", "_")
        framework = cfg.get(subj_key, "")
        if not framework:
            continue
        desc = get_framework_description(framework)
        label = subj.replace("_", " ").title()
        lines.append(f"Standards Framework ({label}): {desc} ({framework})")

    if not lines:
        return ""

    grade_str = ", ".join(grades) if grades else "All grades"
    header = f"State: {state_name} ({state})"
    footer = (
        f"Grades: {grade_str}\n"
        "When generating content, align all objectives, assessments, and materials "
        "to these specific standards. Reference standard codes where applicable."
    )
    return "\n".join([header, *lines, footer])
