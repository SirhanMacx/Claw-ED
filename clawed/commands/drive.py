"""CLI commands for Google Drive integration.

clawed drive auth   — authenticate with Google Drive
clawed drive list   — list files in a folder
clawed drive ingest — ingest curriculum from a Drive folder
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import typer
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

drive_app = typer.Typer(help="Google Drive integration")


def _check_google_deps() -> bool:
    """Check if google optional deps are installed."""
    try:
        import google.auth  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
        return True
    except ImportError:
        console.print(
            "[red]Google Drive dependencies not installed.[/red]\n"
            "Run: [bold]pip install clawed[google][/bold]"
        )
        return False


@drive_app.command()
def auth(
    client_id: str | None = typer.Option(
        None, "--client-id", help="Google OAuth client ID"
    ),
    client_secret: str | None = typer.Option(
        None, "--client-secret", help="Google OAuth client secret"
    ),
    credentials_file: str | None = typer.Option(
        None, "--credentials", "-c",
        help="Path to Google OAuth credentials.json (from Google Cloud Console)"
    ),
) -> None:
    """Authenticate Ed with your Google Drive.

    Get credentials from https://console.cloud.google.com/apis/credentials
    Download the OAuth client JSON and pass it with --credentials.
    """
    if not _check_google_deps():
        raise typer.Exit(1)

    from clawed.agent_core.drive.auth import run_oauth_flow
    try:
        run_oauth_flow(
            client_id=client_id,
            client_secret=client_secret,
            credentials_file=credentials_file,
        )
        console.print("[green]Drive authentication successful![/green]")
        console.print("Ed can now access your Google Drive files.")
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        raise typer.Exit(1) from e


@drive_app.command(name="list")
def list_files(
    folder_id: str | None = typer.Argument(
        None, help="Drive folder ID (default: root)"
    ),
) -> None:
    """List files in a Google Drive folder."""
    if not _check_google_deps():
        raise typer.Exit(1)

    from clawed.agent_core.drive.auth import is_authenticated
    if not is_authenticated():
        console.print("[red]Not authenticated. Run:[/red] clawed drive auth")
        raise typer.Exit(1)

    from clawed.agent_core.drive.client import DriveClient
    client = DriveClient()
    files = client.list_files(folder_id=folder_id or "root")
    if not files:
        console.print("[dim]No files found.[/dim]")
        return
    for f in files:
        icon = "📁" if f.get("mimeType", "").endswith("folder") else "📄"
        console.print(f"  {icon} {f['name']}  [dim]{f['id']}[/dim]")


@drive_app.command()
def ingest(
    folder_url: str = typer.Argument(..., help="Google Drive folder URL or ID"),
) -> None:
    """Ingest curriculum files from a Google Drive folder.

    Downloads files and adds them to Ed's knowledge base.
    """
    if not _check_google_deps():
        raise typer.Exit(1)

    from clawed.agent_core.drive.auth import is_authenticated
    if not is_authenticated():
        console.print("[red]Not authenticated. Run:[/red] clawed drive auth")
        raise typer.Exit(1)

    # Extract folder ID from URL if needed
    folder_id = _extract_folder_id(folder_url)

    from clawed.agent_core.drive.client import DriveClient
    from clawed.agent_core.identity import get_teacher_id
    from clawed.agent_core.memory.curriculum_kb import CurriculumKB

    client = DriveClient()
    teacher_id = get_teacher_id()
    kb = CurriculumKB()

    # Cache dir for downloaded files
    data_dir = os.environ.get("EDUAGENT_DATA_DIR", str(Path.home() / ".eduagent"))
    cache_dir = Path(data_dir) / "drive_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with console.status("[bold]Listing Drive files...[/bold]"):
        files = client.list_files(folder_id=folder_id)

    if not files:
        console.print("[yellow]No files found in that folder.[/yellow]")
        return

    # Filter for supported file types
    supported = {
        "application/pdf",
        "application/vnd.google-apps.document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/markdown",
    }
    ingestable = [f for f in files if f.get("mimeType") in supported]

    if not ingestable:
        console.print("[yellow]No supported files found (PDF, DOCX, PPTX, TXT, MD, Google Docs).[/yellow]")
        return

    console.print(f"Found [bold]{len(ingestable)}[/bold] files to ingest.")

    total_chunks = 0
    for i, f in enumerate(ingestable, 1):
        name = f["name"]
        mime = f.get("mimeType", "")
        console.print(f"  [{i}/{len(ingestable)}] {name}...")

        try:
            # Read file content
            content_data = client.read_file(f["id"])
            content = content_data.get("content", "")
            if not content or len(content.strip()) < 50:
                console.print("    [dim]Skipped (too short or empty)[/dim]")
                continue

            # Index into KB
            chunks = kb.index(
                teacher_id=teacher_id,
                doc_title=name,
                source_path=f"drive://{f['id']}",
                full_text=content,
                metadata={"source": "google_drive", "mime_type": mime},
            )
            total_chunks += chunks
            console.print(f"    [green]✓[/green] {chunks} chunks")
        except Exception as e:
            console.print(f"    [red]✗ {e}[/red]")

    stats = kb.stats(teacher_id)
    console.print(
        f"\n[bold green]Done![/bold green] {total_chunks} new chunks indexed. "
        f"KB now has {stats['doc_count']} docs, {stats['chunk_count']} total chunks."
    )


def _extract_folder_id(url_or_id: str) -> str:
    """Extract folder ID from a Drive URL or return as-is if already an ID."""
    import re
    # Match: https://drive.google.com/drive/folders/FOLDER_ID
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    # Match: https://drive.google.com/drive/u/0/folders/FOLDER_ID
    match = re.search(r"drive/u/\d+/folders/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    # Assume it's already a folder ID
    return url_or_id
