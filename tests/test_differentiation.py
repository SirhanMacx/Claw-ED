"""Tests for differentiation helpers (pure functions, no LLM calls)."""

import json
from unittest.mock import MagicMock

from clawed.differentiation import load_iep_profiles, save_tiered_assignments


def test_load_iep_profiles_single_profile(tmp_path):
    """Load a single IEP profile from a JSON file (dict, not array)."""
    profile_data = {
        "student_name": "Alex",
        "disability_type": "SLD",
        "accommodations": ["extended time", "preferential seating"],
        "modifications": ["reduced question count"],
        "goals": ["improve reading comprehension"],
    }
    path = tmp_path / "iep.json"
    path.write_text(json.dumps(profile_data))

    profiles = load_iep_profiles(path)
    assert len(profiles) == 1
    assert profiles[0].student_name == "Alex"
    assert "extended time" in profiles[0].accommodations


def test_load_iep_profiles_array(tmp_path):
    """Load multiple IEP profiles from a JSON array."""
    profiles_data = [
        {
            "student_name": "Alex",
            "disability_type": "SLD",
            "accommodations": ["extended time"],
            "modifications": [],
            "goals": ["reading comprehension"],
        },
        {
            "student_name": "Jordan",
            "disability_type": "ADHD",
            "accommodations": ["breaks", "fidget tool"],
            "modifications": [],
            "goals": ["focus"],
        },
    ]
    path = tmp_path / "ieps.json"
    path.write_text(json.dumps(profiles_data))

    profiles = load_iep_profiles(path)
    assert len(profiles) == 2
    assert profiles[1].student_name == "Jordan"


def test_save_tiered_assignments(tmp_path):
    """Save tiered assignment items to a JSON file."""
    item1 = MagicMock()
    item1.model_dump.return_value = {
        "item_number": 1,
        "question": "What is 2+2?",
        "answer": "4",
    }
    item2 = MagicMock()
    item2.model_dump.return_value = {
        "item_number": 100,
        "question": "Solve for x: 2x + 3 = 7",
        "answer": "x = 2",
    }

    result_path = save_tiered_assignments([item1, item2], tmp_path, "Addition")
    assert result_path.exists()
    data = json.loads(result_path.read_text())
    assert len(data) == 2
    assert data[0]["item_number"] == 1
    assert data[1]["item_number"] == 100
