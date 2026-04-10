"""Regression tests for auth boundaries — extension, classroom, approvals, bootstrap.

Covers remaining-fixes items 2, 3, 4, and 7 from the final audit.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from clawed.agent_core.context import AgentContext, ToolResult
from clawed.agent_core.tools.base import RISK_WRITE_LOCAL, ToolRegistry


def _ctx() -> AgentContext:
    return AgentContext(
        teacher_id="test",
        config=MagicMock(),
        teacher_profile={},
        persona=None,
        session_history=[],
        improvement_context="",
    )


# ── Fix 2: Extension auth regression tests ──────────────────────────


class TestExtensionAuthRegression:
    """Extension routes must reject unauthenticated requests."""

    @pytest.fixture
    def client(self, monkeypatch):
        """Create a test client WITHOUT localhost bypass."""
        monkeypatch.delenv("EDUAGENT_LOCAL_AUTH_BYPASS", raising=False)
        from fastapi.testclient import TestClient

        from clawed.api.server import create_app

        app = create_app()
        return TestClient(app)

    def test_extension_generate_rejects_no_auth(self, client):
        resp = client.post(
            "/api/extension/generate",
            json={"text": "test", "source_url": "", "source_title": ""},
        )
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"

    def test_extension_add_source_rejects_no_auth(self, client):
        resp = client.post(
            "/api/extension/add-source",
            json={"text": "test", "source_url": "", "source_title": ""},
        )
        assert resp.status_code in (401, 403)

    def test_community_share_rejects_no_auth(self, client):
        resp = client.post(
            "/api/community/share",
            json={"lesson_json": "{}", "subject": "math"},
        )
        assert resp.status_code in (401, 403)

    def test_onboarding_step_rejects_no_auth(self, client):
        resp = client.post(
            "/api/onboarding/step",
            json={"teacher_id": "x", "step": 1},
        )
        assert resp.status_code in (401, 403)


# ── Fix 3: Student classroom split tests ─────────────────────────────


class TestClassroomStudentRoutes:
    """Student routes work without teacher auth; invalid codes fail."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from clawed.api.server import create_app

        app = create_app()
        return TestClient(app)

    def test_classroom_state_invalid_code(self, client):
        resp = client.get("/api/classroom/INVALID123/state")
        data = resp.json()
        assert "error" in data or resp.status_code == 404

    def test_classroom_respond_invalid_code(self, client):
        resp = client.post(
            "/api/classroom/INVALID123/respond",
            params={"student_id": "s1", "response": "test"},
        )
        data = resp.json()
        assert "error" in data or resp.status_code == 404


# ── Fix 4: Standing approval path tests ──────────────────────────────


class TestStandingApprovalPath:
    """Prove get_standing_approval works end-to-end with the registry."""

    def test_get_standing_approval_returns_approved(self, tmp_path):
        from clawed.agent_core.approvals import ApprovalManager

        mgr = ApprovalManager(base_dir=tmp_path)
        # Create and approve an approval for a specific tool
        pa = mgr.create(
            teacher_id="teacher1",
            action_description="Allow export",
            action_payload={"tool_name": "export_document"},
            agent_state={},
            transport="cli",
        )
        mgr.approve(pa.id)

        # Should find the standing approval
        result = mgr.get_standing_approval("teacher1", "export_document")
        assert result is not None
        assert result.status == "approved"

    def test_get_standing_approval_returns_none_when_missing(self, tmp_path):
        from clawed.agent_core.approvals import ApprovalManager

        mgr = ApprovalManager(base_dir=tmp_path)
        result = mgr.get_standing_approval("teacher1", "nonexistent_tool")
        assert result is None

    def test_rejected_approval_not_returned(self, tmp_path):
        from clawed.agent_core.approvals import ApprovalManager

        mgr = ApprovalManager(base_dir=tmp_path)
        pa = mgr.create(
            teacher_id="teacher1",
            action_description="Reject this",
            action_payload={"tool_name": "some_tool"},
            agent_state={},
            transport="cli",
        )
        mgr.reject(pa.id)

        result = mgr.get_standing_approval("teacher1", "some_tool")
        assert result is None  # Rejected does not count

    def test_pending_approval_not_returned(self, tmp_path):
        from clawed.agent_core.approvals import ApprovalManager

        mgr = ApprovalManager(base_dir=tmp_path)
        mgr.create(
            teacher_id="teacher1",
            action_description="Still pending",
            action_payload={"tool_name": "pending_tool"},
            agent_state={},
            transport="cli",
        )

        result = mgr.get_standing_approval("teacher1", "pending_tool")
        assert result is None  # Pending does not count

    @pytest.mark.asyncio
    async def test_registry_allows_tool_with_standing_approval(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Integration: registry executes a gated tool when approval exists."""
        monkeypatch.setenv("CLAWED_AUTO_APPROVE", "0")

        from clawed.agent_core.approvals import ApprovalManager

        # Create standing approval
        mgr = ApprovalManager(base_dir=tmp_path)
        pa = mgr.create(
            teacher_id="test",
            action_description="Allow write",
            action_payload={"tool_name": "approved_write"},
            agent_state={},
            transport="cli",
        )
        mgr.approve(pa.id)

        # Create a write_local tool
        class _ApprovedTool:
            risk_level = RISK_WRITE_LOCAL

            def schema(self):
                return {
                    "type": "function",
                    "function": {
                        "name": "approved_write",
                        "description": "t",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }

            async def execute(self, params, context):
                return ToolResult(text="executed")

        reg = ToolRegistry()
        reg.register(_ApprovedTool())

        # Patch ApprovalManager where it's imported (inside _check_approval)
        with patch(
            "clawed.agent_core.approvals.ApprovalManager",
            return_value=mgr,
        ):
            result = await reg.execute("approved_write", {}, _ctx())

        assert result.text == "executed"


# ── Fix 7: Page auth bootstrap tests ─────────────────────────────────


class TestPageAuthBootstrap:
    """POST /api/auth/bootstrap sets cookie and redirects."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from clawed.api.server import create_app

        app = create_app()
        return TestClient(app)

    def test_valid_token_sets_cookie_and_redirects(self, client):
        from clawed.api.deps import get_api_token

        token = get_api_token()

        resp = client.post(
            "/api/auth/bootstrap",
            data={"token": token},
            follow_redirects=False,
        )
        # Should redirect (303) with cookie set
        assert resp.status_code == 303
        assert "clawed_token" in resp.cookies

    def test_invalid_token_returns_401(self, client):
        resp = client.post(
            "/api/auth/bootstrap",
            data={"token": "wrong_token_value"},
            follow_redirects=False,
        )
        assert resp.status_code == 401

    def test_cookie_grants_page_access(self, client):
        from clawed.api.deps import get_api_token

        token = get_api_token()

        # First: bootstrap to get cookie
        resp1 = client.post(
            "/api/auth/bootstrap",
            data={"token": token},
            follow_redirects=False,
        )
        cookies = resp1.cookies

        # Second: access a protected page with the cookie
        resp2 = client.get("/api/settings", cookies=cookies)
        assert resp2.status_code == 200
