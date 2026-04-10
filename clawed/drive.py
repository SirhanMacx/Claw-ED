"""Google Drive folder ingestion — public API fallback + ZIP mode."""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx

from clawed.ingestor import ingest_directory, ingest_path
from clawed.models import Document


def extract_folder_id(url: str) -> Optional[str]:
    """Extract folder ID from various Google Drive URL formats.

    Supports:
        https://drive.google.com/drive/folders/FOLDER_ID
        https://drive.google.com/drive/folders/FOLDER_ID?usp=sharing
        https://drive.google.com/drive/u/0/folders/FOLDER_ID
        https://drive.google.com/open?id=FOLDER_ID
    """
    patterns = [
        r"drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)",
        r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)",
        r"drive\.google\.com/(?:folderview|file/d)/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


async def _list_drive_files(folder_id: str) -> list[dict]:
    """Try to list files in a public Google Drive folder via the API (no auth)."""
    api_url = "https://www.googleapis.com/drive/v3/files"
    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "fields": "files(id,name,mimeType)",
        "pageSize": "50",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(api_url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("files", [])


async def _download_drive_file(file_id: str, dest: Path) -> None:
    """Download a single file from Google Drive (public, no auth)."""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


# Supported MIME types → file extensions
_MIME_MAP: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt",
    "text/markdown": ".md",
    # Google Docs exports
    "application/vnd.google-apps.document": ".docx",
    "application/vnd.google-apps.presentation": ".pptx",
}


async def ingest_drive_folder(url: str) -> list[Document]:
    """Try to ingest files from a Google Drive folder URL.

    Returns list of Document objects (same format as ingestor.py).
    Falls back gracefully if not publicly accessible.

    Strategy:
        1. Extract folder ID from URL
        2. Try listing files via public Google Drive API
        3. Download supported files to a temp directory
        4. Run ingestor on the temp directory
        5. If API call fails (auth required), return helpful message as exception
    """
    folder_id = extract_folder_id(url)
    if not folder_id:
        raise ValueError(
            "Could not parse a Google Drive folder ID from that URL. "
            "Expected a link like: https://drive.google.com/drive/folders/ABC123"
        )

    try:
        files = await _list_drive_files(folder_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise PermissionError(
                "This Google Drive folder isn't publicly accessible.\n\n"
                "Two options:\n"
                "1. Make the folder public: right-click → Share → 'Anyone with the link'\n"
                "2. Download as ZIP: select all files → ⋮ → Download → then send me the ZIP file path"
            ) from exc
        raise
    except httpx.HTTPError as exc:
        raise ConnectionError("Couldn't reach Google Drive. Check your internet connection and try again.") from exc

    if not files:
        return []

    # Download supported files to a temp directory and ingest
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        downloaded = 0

        for f in files:
            mime = f.get("mimeType", "")
            ext = _MIME_MAP.get(mime)
            if not ext:
                continue
            name = f.get("name", f["id"])
            if not name.endswith(ext):
                name = name + ext
            dest = tmp_path / name
            try:
                if mime.startswith("application/vnd.google-apps."):
                    # Google Docs native format — export instead of direct download
                    export_mime = (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        if ext == ".docx"
                        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    )
                    export_url = f"https://www.googleapis.com/drive/v3/files/{f['id']}/export?mimeType={export_mime}"
                    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                        resp = await client.get(export_url)
                        resp.raise_for_status()
                        dest.write_bytes(resp.content)
                else:
                    await _download_drive_file(f["id"], dest)
                downloaded += 1
            except httpx.HTTPError:
                # Skip files we can't download — don't fail the whole batch
                continue

        if downloaded == 0:
            return []

        return ingest_directory(tmp_path)


def ingest_drive_zip(zip_path: str | Path) -> list[Document]:
    """Ingest a ZIP file downloaded from Google Drive.

    This is the reliable fallback when the Drive folder isn't public.
    Teachers can: select all → Download → get a ZIP.
    """
    path = Path(zip_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"ZIP file not found: {path}")
    if not zipfile.is_zipfile(str(path)):
        raise ValueError(f"Not a valid ZIP file: {path}")
    return ingest_path(path)
