from clawed.api.routes.agent_stream import _append_approval_footer


def test_approval_footer_appends_authoritative_log() -> None:
    text = "No approvals were required."
    result = _append_approval_footer(
        text,
        [
            {
                "approval_id": "abc",
                "tool_name": "brain_dream",
                "risk_level": "write_local",
                "approved": True,
                "always": False,
            }
        ],
    )

    assert "No approvals were required." in result
    assert "Authoritative approval log for this turn:" in result
    assert "- brain_dream: approved; risk=write_local" in result


def test_approval_footer_noops_without_approvals() -> None:
    assert _append_approval_footer("plain final", []) == "plain final"
