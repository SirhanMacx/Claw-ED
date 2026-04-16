"""Google OAuth flow + token persistence for Drive access."""
from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def _default_token_path() -> Path:
    from clawed.paths import data_dir
    return data_dir() / "drive_token.json"

_DEFAULT_TOKEN_PATH = None  # resolved lazily via _default_token_path()

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]


def save_token(token_data: dict[str, Any],
               token_path: Path | None = None) -> None:
    """Persist OAuth token to disk."""
    path = token_path or _default_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    with contextlib.suppress(OSError):
        path.chmod(0o600)


def load_token(token_path: Path | None = None) -> dict[str, Any] | None:
    """Load OAuth token from disk. Returns None if not found."""
    path = token_path or _default_token_path()
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load Drive token: %s", e)
        return None


def is_authenticated(token_path: Path | None = None) -> bool:
    """Check if a valid Drive token exists."""
    return load_token(token_path) is not None


def run_oauth_flow(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    credentials_file: str | None = None,
    token_path: Path | None = None,
) -> None:
    """Run the full Google OAuth2 installed-app flow.

    Priority: credentials_file > client_id+client_secret > env vars.
    Opens a browser for the user to authorize, then saves the token.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise RuntimeError(
            "google-auth-oauthlib not installed. Run: pip install clawed[google]"
        ) from e

    if credentials_file:
        # Use downloaded credentials JSON from Google Cloud Console
        creds_path = Path(credentials_file).expanduser()
        if not creds_path.exists():
            raise FileNotFoundError(f"Credentials file not found: {creds_path}")
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    elif client_id and client_secret:
        # Use provided client ID and secret
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    else:
        # Check env vars
        env_id = os.environ.get("GOOGLE_CLIENT_ID")
        env_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        if env_id and env_secret:
            client_config = {
                "installed": {
                    "client_id": env_id,
                    "client_secret": env_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        else:
            raise RuntimeError(
                "No credentials provided. Either:\n"
                "  1. Pass --credentials <path-to-credentials.json>\n"
                "  2. Pass --client-id and --client-secret\n"
                "  3. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars\n\n"
                "Get credentials at: https://console.cloud.google.com/apis/credentials"
            )

    # Run the local server flow (opens browser)
    creds = flow.run_local_server(port=0, open_browser=True)

    # Save token
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
    save_token(token_data, token_path)
    logger.info("Drive token saved successfully")


def get_auth_url(
    client_id: str | None = None,
    client_secret: str | None = None,
) -> str | None:
    """Generate an OAuth authorization URL for Telegram-initiated auth.

    Returns the URL the teacher should visit to authorize, or None if
    credentials aren't configured.
    """
    cid = client_id or os.environ.get("GOOGLE_CLIENT_ID")
    csecret = client_secret or os.environ.get("GOOGLE_CLIENT_SECRET")
    if not cid or not csecret:
        return None

    import urllib.parse
    params = {
        "client_id": cid,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "access_type": "offline",
    }
    return f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"
