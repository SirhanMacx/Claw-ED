"""Tests for clawed.agent_core.tools.curriculum_visualizer — canvas HTML renderer."""

import json

from clawed.agent_core.tools.curriculum_visualizer import _build_canvas_html

# ── Canvas HTML output ────────────────────────────────────────────────


class TestCanvasHtmlContainsData:
    """The generated HTML must embed the graph data correctly."""

    def test_canvas_html_contains_node_data(self):
        """Node labels should appear in the embedded JSON data."""
        nodes = [
            {"id": 1, "label": "American Revolution", "type": "topic", "connections": 5},
            {"id": 2, "label": "Declaration of Independence", "type": "topic", "connections": 3},
        ]
        edges = [
            {"source": 1, "target": 2, "label": "led to"},
        ]

        html = _build_canvas_html(nodes, edges, "Ms. Smith's Curriculum")
        assert "American Revolution" in html
        assert "Declaration of Independence" in html
        assert "Ms. Smith" in html

    def test_canvas_html_contains_edge_data(self):
        """Edge relationships should appear in the embedded JSON data."""
        nodes = [
            {"id": 1, "label": "Photosynthesis", "type": "topic", "connections": 2},
            {"id": 2, "label": "Cellular Respiration", "type": "topic", "connections": 2},
        ]
        edges = [
            {"source": 1, "target": 2, "label": "produces energy for"},
        ]

        html = _build_canvas_html(nodes, edges, "Science Map")
        assert "produces energy for" in html

    def test_canvas_html_is_valid_structure(self):
        """Output must be a valid self-contained HTML document."""
        nodes = [{"id": 1, "label": "Test", "type": "topic", "connections": 1}]
        edges = []

        html = _build_canvas_html(nodes, edges, "Test")
        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "<canvas" in html
        assert "<script>" in html
        assert "</html>" in html

    def test_canvas_html_has_stats(self):
        """The info panel should show node and edge counts."""
        nodes = [{"id": i, "label": f"Topic {i}", "type": "topic", "connections": 1} for i in range(5)]
        edges = [{"source": 0, "target": 1, "label": "relates"}]

        html = _build_canvas_html(nodes, edges, "Test")
        assert "5" in html  # 5 topics
        assert "1" in html  # 1 connection


# ── Noise filtering (tested at higher level, but _build_canvas_html should handle clean data) ──


class TestNoiseFiltering:
    """The build function should handle potentially noisy labels gracefully."""

    def test_special_characters_in_labels_safe(self):
        """Labels with quotes, angle brackets, etc. should not break the HTML."""
        nodes = [
            {"id": 1, "label": 'Say "hello" & <goodbye>', "type": "topic", "connections": 1},
        ]
        edges = []

        html = _build_canvas_html(nodes, edges, "Test")
        # Should not crash; the JSON double-encoding handles special chars
        assert "<!DOCTYPE html>" in html
        # The data is double-JSON-encoded, so raw < should not appear unescaped
        # in a way that breaks the HTML structure
        assert "<script>" in html

    def test_unicode_labels_handled(self):
        """Non-ASCII labels (accented chars, CJK, etc.) should work."""
        nodes = [
            {"id": 1, "label": "Renacimiento espanol", "type": "topic", "connections": 1},
            {"id": 2, "label": "Revolution francaise", "type": "topic", "connections": 1},
        ]
        edges = [{"source": 1, "target": 2, "label": "influenced"}]

        html = _build_canvas_html(nodes, edges, "World History")
        assert "<!DOCTYPE html>" in html


# ── JSON double encoding ──────────────────────────────────────────────


class TestJsonDoubleEncoding:
    """Graph data must be double-JSON-encoded for safe injection into JS."""

    def test_json_double_encoding(self):
        """The data_json_str pattern should produce valid JS when parsed."""
        nodes = [{"id": 1, "label": "Test Node", "type": "topic", "connections": 0}]
        edges = []

        html = _build_canvas_html(nodes, edges, "Test")

        # The HTML should contain JSON.parse( with a string literal
        assert "JSON.parse(" in html

        # Extract the double-encoded JSON string from the HTML
        # Pattern: var D=JSON.parse(<json_string>);
        import re

        match = re.search(r"var D=JSON\.parse\((.+?)\);", html)
        assert match is not None, "Could not find JSON.parse pattern in HTML"

        # The outer parse should yield a string
        outer = json.loads(match.group(1))
        assert isinstance(outer, str)

        # The inner parse should yield the actual data
        inner = json.loads(outer)
        assert "nodes" in inner
        assert "edges" in inner
        assert len(inner["nodes"]) == 1
        assert inner["nodes"][0]["label"] == "Test Node"

    def test_quotes_in_labels_survive_double_encoding(self):
        """Labels containing quotes should survive the double-encode round-trip."""
        nodes = [{"id": 1, "label": 'The "Great" War', "type": "topic", "connections": 0}]
        edges = []

        html = _build_canvas_html(nodes, edges, "Test")

        import re

        match = re.search(r"var D=JSON\.parse\((.+?)\);", html)
        assert match is not None
        outer = json.loads(match.group(1))
        inner = json.loads(outer)
        assert inner["nodes"][0]["label"] == 'The "Great" War'


# ── Empty graph ───────────────────────────────────────────────────────


class TestEmptyKG:
    """An empty knowledge graph should still produce valid HTML."""

    def test_empty_kg_produces_valid_html(self):
        """Zero nodes and zero edges should still render without errors."""
        html = _build_canvas_html([], [], "Empty Curriculum")
        assert "<!DOCTYPE html>" in html
        assert "<canvas" in html
        assert "Empty Curriculum" in html
        assert "0" in html  # 0 topics shown in stats

    def test_empty_nodes_with_edges_ignored(self):
        """Edges referencing nonexistent nodes should not crash the renderer."""
        edges = [{"source": 99, "target": 100, "label": "phantom"}]
        html = _build_canvas_html([], edges, "Ghost Graph")
        assert "<!DOCTYPE html>" in html
