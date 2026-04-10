"""Tests for GatewayResponse — the transport-agnostic response type."""

from pathlib import Path

from clawed.gateway_response import Button, GatewayResponse


class TestGatewayResponse:
    def test_text_only_response(self):
        r = GatewayResponse(text="Hello teacher")
        assert r.text == "Hello teacher"
        assert r.files == []
        assert r.buttons == []
        assert r.typing is False
        assert r.progress == ""

    def test_response_with_files(self):
        r = GatewayResponse(text="Here's your lesson", files=[Path("/tmp/lesson.pptx")])
        assert len(r.files) == 1
        assert r.files[0].name == "lesson.pptx"

    def test_response_with_buttons(self):
        b = Button(label="Rate 5★", callback_data="rate:abc:5")
        r = GatewayResponse(text="Rate this lesson?", buttons=[b])
        assert r.buttons[0].label == "Rate 5★"
        assert r.buttons[0].callback_data == "rate:abc:5"

    def test_button_defaults(self):
        b = Button(label="Click me", callback_data="action:do_thing")
        assert b.url is None

    def test_progress_response(self):
        r = GatewayResponse(text="", typing=True, progress="Generating lesson...")
        assert r.typing is True
        assert r.progress == "Generating lesson..."

    def test_empty_response(self):
        r = GatewayResponse.empty()
        assert r.text == ""
        assert r.files == []

    def test_response_has_content(self):
        assert GatewayResponse(text="hi").has_content is True
        assert GatewayResponse(text="").has_content is False
        assert GatewayResponse(text="", files=[Path("/tmp/x.pdf")]).has_content is True

    def test_button_rows(self):
        """Buttons can be grouped into rows for keyboard layout."""
        row1 = [
            Button(label="Slides", callback_data="export:slides"),
            Button(label="Handout", callback_data="export:handout"),
        ]
        row2 = [Button(label="Rate", callback_data="rate:prompt")]
        r = GatewayResponse(text="Done!", button_rows=[row1, row2])
        assert len(r.button_rows) == 2
        assert len(r.button_rows[0]) == 2
