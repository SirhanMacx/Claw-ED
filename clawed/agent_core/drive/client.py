"""Google Drive API client with rate limiting."""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path
from typing import Any

from clawed.agent_core.drive.auth import is_authenticated, load_token

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_per_hour: int = 60) -> None:
        self._max = max_per_hour
        self._timestamps: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._timestamps and now - self._timestamps[0] > 3600:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._max:
            return False
        self._timestamps.append(now)
        return True


class DriveClient:
    """Google Drive file operations with rate limiting."""

    def __init__(
        self,
        token_path: Path | None = None,
        max_per_hour: int = 60,
    ) -> None:
        self._token_path = token_path
        self._limiter = RateLimiter(max_per_hour=max_per_hour)

    def _check_auth(self) -> None:
        if not is_authenticated(self._token_path):
            raise RuntimeError("Google Drive not authenticated. Run: clawed drive auth")

    def _check_rate(self) -> None:
        if not self._limiter.allow():
            raise RuntimeError("Drive rate limit exceeded. Try again later.")

    def _get_service(self):
        """Build the Google Drive API service.

        Requires: pip install 'clawed[google]'
        """
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError("Google Drive support requires: pip install 'clawed[google]'")

        token_data = load_token(self._token_path)
        creds = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
        )
        return build("drive", "v3", credentials=creds)

    async def list_files(
        self,
        folder_id: str = "root",
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """List files in a Drive folder."""
        self._check_auth()
        self._check_rate()
        service = self._get_service()
        query = f"'{folder_id}' in parents and trashed=false"
        results = (
            service.files()
            .list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, mimeType, modifiedTime)",
            )
            .execute()
        )
        return results.get("files", [])

    async def upload_file(
        self,
        file_path: Path,
        folder_id: str = "root",
        file_name: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file to Drive."""
        self._check_auth()
        self._check_rate()
        service = self._get_service()
        from googleapiclient.http import MediaFileUpload

        name = file_name or file_path.name
        file_metadata = {"name": name, "parents": [folder_id]}
        media = MediaFileUpload(str(file_path))
        result = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink",
            )
            .execute()
        )
        return result

    async def create_folder(
        self,
        name: str,
        parent_id: str = "root",
    ) -> dict[str, Any]:
        """Create a folder in Drive."""
        self._check_auth()
        self._check_rate()
        service = self._get_service()
        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        result = (
            service.files()
            .create(
                body=file_metadata,
                fields="id, name",
            )
            .execute()
        )
        return result

    async def create_slides(
        self,
        title: str,
        content: str,
        folder_id: str = "root",
    ) -> dict[str, Any]:
        """Create a native Google Slides presentation."""
        self._check_auth()
        self._check_rate()
        service = self._get_service()
        file_metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.presentation",
            "parents": [folder_id],
        }
        result = (
            service.files()
            .create(
                body=file_metadata,
                fields="id, name, webViewLink",
            )
            .execute()
        )
        return result

    async def create_doc(
        self,
        title: str,
        content: str,
        folder_id: str = "root",
    ) -> dict[str, Any]:
        """Create a native Google Doc."""
        self._check_auth()
        self._check_rate()
        service = self._get_service()
        file_metadata = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        }
        result = (
            service.files()
            .create(
                body=file_metadata,
                fields="id, name, webViewLink",
            )
            .execute()
        )
        return result

    async def read_file(self, file_id: str) -> dict[str, Any]:
        """Read file metadata and content from Drive."""
        self._check_auth()
        self._check_rate()
        service = self._get_service()
        metadata = (
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, modifiedTime",
            )
            .execute()
        )
        # For text-based files, try to export content
        content = ""
        mime = metadata.get("mimeType", "")
        if "document" in mime or "spreadsheet" in mime or "presentation" in mime:
            try:
                export = (
                    service.files()
                    .export(
                        fileId=file_id,
                        mimeType="text/plain",
                    )
                    .execute()
                )
                content = export.decode("utf-8") if isinstance(export, bytes) else str(export)
            except Exception:
                pass
        return {**metadata, "content": content}
