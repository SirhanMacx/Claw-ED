"""Tests for NLAH failure taxonomy."""

from clawed.failure_codes import FailureCode


class TestFailureCodes:
    def test_all_nlah_codes_exist(self):
        """All 13 NLAH failure codes exist and are strings."""
        expected = [
            "NO_PERSONA",
            "SCHEMA_ERROR",
            "TOPIC_DRIFT",
            "DEMO_FIXTURE",
            "EXPORT_INCOMPLETE",
            "EXPORT_ERROR",
            "REVIEW_FAILED",
            "CONTEXT_EXCEEDED",
            "API_FAILURE",
            "VOICE_MISMATCH",
            "PERSONA_PARSE_ERROR",
            "KB_SEARCH_FAILED",
            "ASSET_SEARCH_FAILED",
        ]
        for code in expected:
            assert hasattr(FailureCode, code), f"Missing: {code}"
            assert isinstance(FailureCode[code].value, str)

    def test_codes_are_string_enum(self):
        """FailureCode members are usable as strings (str, Enum)."""
        assert isinstance(FailureCode.API_FAILURE, str)
        assert FailureCode.API_FAILURE == "API_FAILURE"
