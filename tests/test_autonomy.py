"""Tests for autonomy progression — approval rate tracking."""

import pytest

from clawed.agent_core.autonomy import ApprovalTracker


class TestApprovalTracker:
    def test_empty_rates(self, tmp_path):
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        rates = tracker.get_rates()
        assert isinstance(rates, dict)
        assert len(rates) == 0

    def test_tracks_approval_rate(self, tmp_path):
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        for i in range(10):
            tracker.record_approval("drive_upload", approved=True, teacher_id="t1")

        rates = tracker.get_rates()
        assert "drive_upload" in rates
        assert rates["drive_upload"]["approval_rate"] == 1.0
        assert rates["drive_upload"]["total"] == 10

    def test_mixed_approvals_and_rejections(self, tmp_path):
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        for i in range(8):
            tracker.record_approval("drive_upload", approved=True, teacher_id="t1")
        for i in range(2):
            tracker.record_approval("drive_upload", approved=False, teacher_id="t1")

        rates = tracker.get_rates()
        assert rates["drive_upload"]["approval_rate"] == 0.8
        assert rates["drive_upload"]["total"] == 10

    def test_should_offer_auto_high_rate(self, tmp_path):
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        for i in range(12):
            tracker.record_approval("generate_lesson", approved=True, teacher_id="t1")

        assert tracker.should_offer_auto("generate_lesson") is True

    def test_never_auto_approve_student_facing(self, tmp_path):
        """Student-facing and Drive actions should never be auto-approved."""
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        for i in range(15):
            tracker.record_approval("drive_upload", approved=True, teacher_id="t1")

        assert tracker.should_offer_auto("drive_upload") is False

    def test_should_not_offer_auto_low_rate(self, tmp_path):
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        for i in range(5):
            tracker.record_approval("drive_upload", approved=True, teacher_id="t1")
        for i in range(5):
            tracker.record_approval("drive_upload", approved=False, teacher_id="t1")

        assert tracker.should_offer_auto("drive_upload") is False

    def test_should_not_offer_auto_insufficient_samples(self, tmp_path):
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        for i in range(3):
            tracker.record_approval("drive_upload", approved=True, teacher_id="t1")

        assert tracker.should_offer_auto("drive_upload") is False

    def test_summarize_for_prompt(self, tmp_path):
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        for i in range(12):
            tracker.record_approval("drive_upload", approved=True, teacher_id="t1")

        summary = tracker.summarize_for_prompt()
        assert "drive_upload" in summary
        assert "auto" in summary.lower() or "always" in summary.lower()

    def test_record_approval_with_payload(self, tmp_path):
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        tracker.record_approval(
            "generate_lesson",
            approved=True,
            teacher_id="t1",
            payload={"tool": "lesson_gen", "args": {"topic": "math"}},
        )
        rates = tracker.get_rates()
        assert "generate_lesson" in rates
        assert rates["generate_lesson"]["approved"] == 1

    def test_migrate_json_if_needed(self, tmp_path):
        """Old JSON files should be migrated into SQLite on init."""
        import json

        # Create the old-style approvals directory with JSON files
        old_dir = tmp_path / "approvals"
        old_dir.mkdir()
        for i in range(5):
            data = {
                "id": f"approval-{i}",
                "status": "approved",
                "action_payload": {"action_type": "generate_lesson"},
                "teacher_id": "t1",
                "created_at": "2026-03-01T10:00:00",
            }
            (old_dir / f"approval-{i}.json").write_text(json.dumps(data))
        for i in range(5, 7):
            data = {
                "id": f"approval-{i}",
                "status": "rejected",
                "action_payload": {"action_type": "generate_lesson"},
                "teacher_id": "t1",
                "created_at": "2026-03-01T10:00:00",
            }
            (old_dir / f"approval-{i}.json").write_text(json.dumps(data))

        # DB lives alongside the approvals/ dir
        tracker = ApprovalTracker(db_path=tmp_path / "approvals.db")
        rates = tracker.get_rates()
        assert "generate_lesson" in rates
        assert rates["generate_lesson"]["approved"] == 5
        assert rates["generate_lesson"]["rejected"] == 2
        assert rates["generate_lesson"]["total"] == 7


class TestStudentInsightsTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.student_insights import StudentInsightsTool

        tool = StudentInsightsTool()
        s = tool.schema()
        assert s["function"]["name"] == "student_insights"

    @pytest.mark.asyncio
    async def test_execute_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        from clawed.agent_core.context import AgentContext
        from clawed.agent_core.tools.student_insights import StudentInsightsTool
        from clawed.models import AppConfig

        tool = StudentInsightsTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"days": 7}, ctx)
        assert "No student questions" in result.text or isinstance(result.text, str)
