"""Tests for clawed.drive — Google Drive folder ingestion."""

from __future__ import annotations

import asyncio
import tempfile
import zipfile
from pathlib import Path

import pytest

from clawed.drive import extract_folder_id, ingest_drive_zip


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    return asyncio.run(coro)


class TestExtractFolderId:
    def test_standard_url(self):
        url = "https://drive.google.com/drive/folders/1ABCdef_GHI-jkl"
        assert extract_folder_id(url) == "1ABCdef_GHI-jkl"

    def test_url_with_sharing_param(self):
        url = "https://drive.google.com/drive/folders/1ABCdef_GHI-jkl?usp=sharing"
        assert extract_folder_id(url) == "1ABCdef_GHI-jkl"

    def test_url_with_user_path(self):
        url = "https://drive.google.com/drive/u/0/folders/1ABCdef_GHI-jkl"
        assert extract_folder_id(url) == "1ABCdef_GHI-jkl"

    def test_open_id_format(self):
        url = "https://drive.google.com/open?id=1ABCdef_GHI-jkl"
        assert extract_folder_id(url) == "1ABCdef_GHI-jkl"

    def test_invalid_url(self):
        assert extract_folder_id("https://example.com/not-a-drive-link") is None

    def test_empty_string(self):
        assert extract_folder_id("") is None

    def test_plain_text(self):
        assert extract_folder_id("my google drive folder") is None


class TestIngestDriveZip:
    def test_ingest_zip_with_txt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "lessons.zip"
            with zipfile.ZipFile(str(zip_path), "w") as zf:
                zf.writestr("lesson1.txt", "Today we will learn about fractions.")
                zf.writestr("lesson2.txt", "Photosynthesis converts light energy to chemical energy.")
            docs = ingest_drive_zip(zip_path)
            assert len(docs) == 2
            titles = {d.title.lower() for d in docs}
            assert "lesson1" in titles or "lesson 1" in titles

    def test_ingest_zip_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            ingest_drive_zip("/tmp/does_not_exist_edu_test.zip")

    def test_ingest_zip_not_a_zip(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(b"this is not a zip file")
            f.flush()
            with pytest.raises(ValueError, match="Not a valid ZIP"):
                ingest_drive_zip(f.name)

    def test_ingest_zip_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "empty.zip"
            with zipfile.ZipFile(str(zip_path), "w") as zf:
                zf.writestr("image.png", b"\x89PNG fake image data")
            docs = ingest_drive_zip(zip_path)
            assert docs == []


class TestIngestDriveFolder:
    def test_invalid_url_raises(self):
        from clawed.drive import ingest_drive_folder

        with pytest.raises(ValueError, match="Could not parse"):
            _run(ingest_drive_folder("https://example.com/not-drive"))


class TestDriveAuth:
    def test_token_save_and_load(self, tmp_path):
        from clawed.agent_core.drive.auth import load_token, save_token

        token_data = {
            "access_token": "ya29.abc",
            "refresh_token": "1//xyz",
            "expiry": "2026-04-01T00:00:00",
        }
        save_token(token_data, token_path=tmp_path / "drive_token.json")
        loaded = load_token(token_path=tmp_path / "drive_token.json")
        assert loaded["access_token"] == "ya29.abc"

    def test_load_token_missing(self, tmp_path):
        from clawed.agent_core.drive.auth import load_token

        result = load_token(token_path=tmp_path / "nonexistent.json")
        assert result is None

    def test_is_authenticated(self, tmp_path):
        from clawed.agent_core.drive.auth import is_authenticated, save_token

        assert not is_authenticated(token_path=tmp_path / "nope.json")
        save_token(
            {"access_token": "test", "refresh_token": "test"},
            token_path=tmp_path / "token.json",
        )
        assert is_authenticated(token_path=tmp_path / "token.json")


class TestRateLimiter:
    def test_allows_initial(self):
        from clawed.agent_core.drive.client import RateLimiter

        rl = RateLimiter(max_per_hour=100)
        assert rl.allow()

    def test_blocks_excess(self):
        from clawed.agent_core.drive.client import RateLimiter

        rl = RateLimiter(max_per_hour=2)
        assert rl.allow()
        assert rl.allow()
        assert not rl.allow()


class TestDriveClient:
    @pytest.mark.asyncio
    async def test_not_authenticated(self, tmp_path):
        from clawed.agent_core.drive.client import DriveClient

        client = DriveClient(token_path=tmp_path / "nope.json")
        with pytest.raises(RuntimeError, match="not authenticated"):
            await client.list_files()

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, tmp_path):
        from clawed.agent_core.drive.auth import save_token
        from clawed.agent_core.drive.client import DriveClient

        # Create a token so auth check passes
        save_token({"access_token": "test", "refresh_token": "test"}, token_path=tmp_path / "token.json")
        client = DriveClient(token_path=tmp_path / "token.json", max_per_hour=0)
        with pytest.raises(RuntimeError, match="rate limit"):
            await client.list_files()


class TestDriveTools:
    def test_drive_upload_schema(self):
        from clawed.agent_core.tools.drive_upload import DriveUploadTool

        tool = DriveUploadTool()
        s = tool.schema()
        assert s["function"]["name"] == "drive_upload"
        assert "file_path" in s["function"]["parameters"]["properties"]

    def test_drive_list_schema(self):
        from clawed.agent_core.tools.drive_list import DriveListTool

        tool = DriveListTool()
        s = tool.schema()
        assert s["function"]["name"] == "drive_list"

    def test_drive_organize_schema(self):
        from clawed.agent_core.tools.drive_organize import DriveOrganizeTool

        tool = DriveOrganizeTool()
        s = tool.schema()
        assert s["function"]["name"] == "drive_organize"

    def test_auto_discovery_finds_drive_tools(self):
        from clawed.agent_core.tools.base import ToolRegistry

        reg = ToolRegistry()
        reg.discover(Path(__file__).parent.parent / "clawed" / "agent_core" / "tools")
        names = reg.tool_names()
        assert "drive_upload" in names
        assert "drive_list" in names
        assert "drive_organize" in names
        assert len(names) >= 17  # 14 original + 3 drive

    @pytest.mark.asyncio
    async def test_drive_upload_not_authenticated(self, tmp_path):
        from clawed.agent_core.context import AgentContext
        from clawed.agent_core.tools.drive_upload import DriveUploadTool
        from clawed.models import AppConfig

        tool = DriveUploadTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        # Should return error ToolResult, not crash
        result = await tool.execute({"file_path": "/tmp/nonexistent.pdf"}, ctx)
        text = result.text.lower()
        assert "not authenticated" in text or "error" in text or "failed" in text


class TestDriveIngestTool:
    def test_schema_valid(self):
        from clawed.agent_core.tools.drive_ingest import DriveIngestTool

        tool = DriveIngestTool()
        schema = tool.schema()
        assert schema["function"]["name"] == "drive_ingest"
        assert "folder_id" in schema["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_not_authenticated_returns_message(self, tmp_path):
        from clawed.agent_core.context import AgentContext
        from clawed.agent_core.tools.drive_ingest import DriveIngestTool
        from clawed.models import AppConfig

        tool = DriveIngestTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"folder_id": "abc123"}, ctx)
        text = result.text.lower()
        assert "not set up" in text or "auth" in text or "drive" in text


class TestExtractFolderIdCommand:
    def test_plain_id(self):
        from clawed.commands.drive import _extract_folder_id

        assert _extract_folder_id("1abc2def3ghi") == "1abc2def3ghi"

    def test_standard_url(self):
        from clawed.commands.drive import _extract_folder_id

        assert _extract_folder_id("https://drive.google.com/drive/folders/1abc2def") == "1abc2def"

    def test_url_with_user(self):
        from clawed.commands.drive import _extract_folder_id

        assert _extract_folder_id("https://drive.google.com/drive/u/0/folders/1abc2def") == "1abc2def"


class TestDriveExtendedTools:
    def test_drive_create_slides_schema(self):
        from clawed.agent_core.tools.drive_create_slides import DriveCreateSlidesTool

        s = DriveCreateSlidesTool().schema()
        assert s["function"]["name"] == "drive_create_slides"
        assert "title" in s["function"]["parameters"]["properties"]

    def test_drive_create_doc_schema(self):
        from clawed.agent_core.tools.drive_create_doc import DriveCreateDocTool

        s = DriveCreateDocTool().schema()
        assert s["function"]["name"] == "drive_create_doc"

    def test_drive_read_schema(self):
        from clawed.agent_core.tools.drive_read import DriveReadTool

        s = DriveReadTool().schema()
        assert s["function"]["name"] == "drive_read"
        assert "file_id" in s["function"]["parameters"]["properties"]

    @pytest.mark.asyncio
    async def test_drive_create_slides_not_authenticated(self, tmp_path):
        from clawed.agent_core.context import AgentContext
        from clawed.agent_core.tools.drive_create_slides import DriveCreateSlidesTool
        from clawed.models import AppConfig

        tool = DriveCreateSlidesTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"title": "Test Slides", "content": "Hello"}, ctx)
        assert "not authenticated" in result.text.lower() or "failed" in result.text.lower()

    @pytest.mark.asyncio
    async def test_drive_create_doc_not_authenticated(self, tmp_path):
        from clawed.agent_core.context import AgentContext
        from clawed.agent_core.tools.drive_create_doc import DriveCreateDocTool
        from clawed.models import AppConfig

        tool = DriveCreateDocTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"title": "Test Doc", "content": "Hello"}, ctx)
        assert "not authenticated" in result.text.lower() or "failed" in result.text.lower()

    @pytest.mark.asyncio
    async def test_drive_read_not_authenticated(self, tmp_path):
        from clawed.agent_core.context import AgentContext
        from clawed.agent_core.tools.drive_read import DriveReadTool
        from clawed.models import AppConfig

        tool = DriveReadTool()
        ctx = AgentContext(
            teacher_id="t1",
            config=AppConfig(),
            teacher_profile={},
            persona=None,
            session_history=[],
            improvement_context="",
        )
        result = await tool.execute({"file_id": "abc123"}, ctx)
        assert "not authenticated" in result.text.lower() or "failed" in result.text.lower()
