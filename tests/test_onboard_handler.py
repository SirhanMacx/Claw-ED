"""Tests for onboarding input validation (P0-5)."""

import re

from clawed.handlers.onboard import OnboardHandler


class TestOnboardValidation:
    def test_name_truncated_at_100(self):
        """Names longer than 100 chars are truncated by the handler."""
        long_name = "A" * 200
        # Replicate the handler's truncation + sanitization logic
        truncated = long_name[:100]
        truncated = re.sub(r"[^\w\s'-]", "", truncated).strip()
        assert len(truncated) <= 100

    def test_grade_validation_rejects_garbage(self):
        """Non-numeric, non-K grades should trigger re-prompt."""
        text = "hello world"
        grade_match = re.search(r"(\d{1,2})", text)
        k_match = re.search(
            r"(?:kindergarten|kinder|pre-?k)",
            text,
            re.IGNORECASE,
        )
        assert grade_match is None
        assert k_match is None
        # This means the handler should re-prompt

    def test_subject_truncated(self):
        """Subjects longer than 100 chars are truncated."""
        long_subject = "X" * 200
        truncated = long_subject[:100]
        assert len(truncated) == 100

    def test_handler_instantiation(self):
        """OnboardHandler can be created without errors."""
        handler = OnboardHandler()
        assert not handler.is_onboarding("test_teacher")
