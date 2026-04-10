"""Tests for the approval gate persistence and lifecycle."""

from clawed.agent_core.approvals import ApprovalManager, PendingApproval


class TestPendingApproval:
    def test_to_json_roundtrip(self):
        pa = PendingApproval(
            teacher_id="t1",
            action_description="Upload 5 lessons to Drive",
            action_payload={"tool": "drive_upload", "args": {"path": "/lessons"}},
            agent_state={"history": [{"role": "user", "content": "prep my week"}]},
            transport="telegram",
        )
        data = pa.to_dict()
        loaded = PendingApproval.from_dict(data)
        assert loaded.id == pa.id
        assert loaded.teacher_id == "t1"
        assert loaded.status == "pending"
        assert loaded.action_payload["tool"] == "drive_upload"

    def test_auto_generates_id(self):
        pa = PendingApproval(
            teacher_id="t1",
            action_description="test",
            action_payload={},
            agent_state={},
            transport="cli",
        )
        assert len(pa.id) > 0


class TestApprovalManager:
    def test_create_and_load(self, tmp_path):
        mgr = ApprovalManager(base_dir=tmp_path)
        pa = mgr.create(
            teacher_id="t1",
            action_description="Upload lessons",
            action_payload={"tool": "upload"},
            agent_state={"history": []},
            transport="telegram",
        )
        loaded = mgr.load(pa.id)
        assert loaded is not None
        assert loaded.action_description == "Upload lessons"

    def test_approve(self, tmp_path):
        mgr = ApprovalManager(base_dir=tmp_path)
        pa = mgr.create(
            teacher_id="t1",
            action_description="test",
            action_payload={},
            agent_state={},
            transport="cli",
        )
        mgr.approve(pa.id)
        loaded = mgr.load(pa.id)
        assert loaded.status == "approved"

    def test_reject(self, tmp_path):
        mgr = ApprovalManager(base_dir=tmp_path)
        pa = mgr.create(
            teacher_id="t1",
            action_description="test",
            action_payload={},
            agent_state={},
            transport="cli",
        )
        mgr.reject(pa.id)
        loaded = mgr.load(pa.id)
        assert loaded.status == "rejected"

    def test_load_nonexistent_returns_none(self, tmp_path):
        mgr = ApprovalManager(base_dir=tmp_path)
        assert mgr.load("nonexistent-id") is None

    def test_pending_for_teacher(self, tmp_path):
        mgr = ApprovalManager(base_dir=tmp_path)
        mgr.create(teacher_id="t1", action_description="a", action_payload={}, agent_state={}, transport="cli")
        mgr.create(teacher_id="t1", action_description="b", action_payload={}, agent_state={}, transport="cli")
        mgr.create(teacher_id="t2", action_description="c", action_payload={}, agent_state={}, transport="cli")
        pending = mgr.pending_for_teacher("t1")
        assert len(pending) == 2

    def test_expire_old(self, tmp_path):
        mgr = ApprovalManager(base_dir=tmp_path)
        pa = mgr.create(
            teacher_id="t1",
            action_description="old",
            action_payload={},
            agent_state={},
            transport="cli",
            timeout_hours=0,  # expires immediately
        )
        expired = mgr.expire_old()
        assert len(expired) >= 1
        loaded = mgr.load(pa.id)
        assert loaded.status == "expired"
