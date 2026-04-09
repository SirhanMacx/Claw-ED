"""Tests for clawed.search — web search for teachers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from clawed.models import TeacherPersona
from clawed.search import (
    _add_edu_framing,
    _format_results,
    _get_tavily_key,
    find_lesson_resource,
    search_for_teacher,
    search_standards_web,
)


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    return asyncio.run(coro)


# ── Helpers ────────────────────────────────────────────────────────────


class TestAddEduFraming:
    def test_strips_command_prefix(self):
        result = _add_edu_framing("search for climate change articles")
        assert result.startswith("climate change articles")

    def test_adds_teaching_resource(self):
        result = _add_edu_framing("photosynthesis")
        assert "teaching resource" in result

    def test_includes_persona_grade(self):
        persona = TeacherPersona(grade_levels=["8"], subject_area="Science")
        result = _add_edu_framing("photosynthesis", persona)
        assert "grade 8" in result
        assert "Science" in result

    def test_no_persona(self):
        result = _add_edu_framing("fractions", None)
        assert "fractions" in result
        assert "teaching resource" in result


class TestFormatResults:
    def test_empty_results(self):
        assert "No results found" in _format_results([])

    def test_formats_up_to_3(self):
        results = [
            {"title": f"Result {i}", "url": f"https://example.com/{i}", "snippet": f"Snippet {i}"}
            for i in range(5)
        ]
        formatted = _format_results(results, max_results=3)
        assert "Result 0" in formatted
        assert "Result 2" in formatted
        assert "Result 4" not in formatted

    def test_includes_title_and_url(self):
        results = [{"title": "Great Resource", "url": "https://example.com", "snippet": "A useful thing"}]
        formatted = _format_results(results)
        assert "Great Resource" in formatted
        assert "https://example.com" in formatted
        assert "A useful thing" in formatted

    def test_handles_missing_fields(self):
        results = [{"title": "Only Title"}]
        formatted = _format_results(results)
        assert "Only Title" in formatted

    def test_header(self):
        results = [{"title": "T", "url": "u", "snippet": "s"}]
        formatted = _format_results(results)
        assert "Search Results" in formatted


class TestGetTavilyKey:
    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test123")
        assert _get_tavily_key() == "tvly-test123"

    def test_returns_none_when_missing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        # Point data_dir to tmp_path (no config.json exists there)
        monkeypatch.setenv("EDUAGENT_DATA_DIR", str(tmp_path))
        result = _get_tavily_key()
        assert result is None


# ── Main functions (with mocked HTTP) ─────────────────────────────────


def _make_mock_response(json_data=None, text=""):
    """Create a mock httpx response (sync .json(), sync .raise_for_status())."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


def _make_mock_client(mock_response):
    """Create a mock httpx.AsyncClient context manager returning mock_response."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post.return_value = mock_response
    mock_client.get.return_value = mock_response
    return mock_client


class TestSearchForTeacher:
    def test_returns_formatted_results_tavily(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        mock_response = _make_mock_response(json_data={
            "results": [
                {"title": "Photosynthesis Lesson", "url": "https://edu.com/photo", "content": "A great resource."}
            ]
        })

        with patch("clawed.search.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(mock_response)
            result = _run(search_for_teacher("photosynthesis activities"))
            assert "Photosynthesis Lesson" in result
            assert "https://edu.com/photo" in result

    def test_falls_back_to_ddg(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

        ddg_html = """
        <div class="result">
            <a class="result__a" href="https://example.com/lesson">Great Lesson Plan</a>
            <a class="result__snippet">This is a snippet about teaching.</a>
        </div>
        """
        mock_response = _make_mock_response(text=ddg_html)

        with patch("clawed.search._get_tavily_key", return_value=None):
            with patch("clawed.search.httpx.AsyncClient") as mock_client_cls:
                mock_client_cls.return_value = _make_mock_client(mock_response)
                result = _run(search_for_teacher("photosynthesis"))
                assert "Great Lesson Plan" in result

    def test_handles_http_error(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)

        with patch("clawed.search._get_tavily_key", return_value=None):
            with patch("clawed.search.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post.side_effect = httpx.HTTPError("connection failed")
                mock_client_cls.return_value = mock_client

                result = _run(search_for_teacher("test query"))
                assert "temporarily unavailable" in result


class TestSearchStandardsWeb:
    def test_returns_standards_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        mock_response = _make_mock_response(json_data={
            "results": [{"title": "NGSS Grade 8 Standards", "url": "https://ngss.org", "content": "Standards list."}]
        })

        with patch("clawed.search.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(mock_response)
            result = _run(search_standards_web("8", "Science"))
            assert "NGSS" in result


class TestFindLessonResource:
    def test_returns_resource_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        mock_response = _make_mock_response(json_data={
            "results": [{"title": "Photosynthesis Lab Activity", "url": "https://edu.com/lab", "content": "Hands-on."}]
        })

        with patch("clawed.search.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(mock_response)
            result = _run(find_lesson_resource("photosynthesis", "8"))
            assert "Photosynthesis Lab Activity" in result
            assert "Grade 8" in result
