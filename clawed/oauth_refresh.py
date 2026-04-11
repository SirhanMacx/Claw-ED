"""OAuth token refresh for Claude Code credentials.

Automatically refreshes expired or near-expired OAuth tokens before
API calls. Uses the same refresh flow as Claude Code CLI.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_SCOPES = "user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload"

# Refresh when less than 10 minutes remaining
REFRESH_THRESHOLD_SECONDS = 600


def get_oauth_token() -> str | None:
    """Get a valid OAuth token, refreshing if needed.

    Returns the access token string, or None if no OAuth credentials exist.
    """
    if not CREDENTIALS_PATH.exists():
        return None

    try:
        creds = json.loads(CREDENTIALS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    oauth = creds.get("claudeAiOauth")
    if not oauth or not oauth.get("accessToken"):
        return None

    # Check if token needs refresh
    expires_at = oauth.get("expiresAt", 0)
    now_ms = int(time.time() * 1000)
    remaining_ms = expires_at - now_ms

    if remaining_ms < REFRESH_THRESHOLD_SECONDS * 1000:
        logger.info("OAuth token expiring in %ds, refreshing...", remaining_ms // 1000)
        refreshed = _refresh_token(oauth.get("refreshToken"))
        if refreshed:
            return refreshed
        # If refresh fails, try the current token anyway
        logger.warning("Token refresh failed, using existing token")

    return oauth["accessToken"]


def _refresh_token(refresh_token: str | None) -> str | None:
    """Refresh an OAuth token and save the new credentials."""
    if not refresh_token:
        return None

    try:
        resp = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

        if resp.status_code == 400:
            body = resp.text[:200]
            if "invalid_grant" in body:
                logger.warning(
                    "OAuth refresh token expired. Run 'claude login' to re-authenticate."
                )
            else:
                logger.warning("Token refresh returned 400: %s", body)
            return None

        if resp.status_code != 200:
            logger.warning("Token refresh returned %d: %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        new_token = data["access_token"]
        new_refresh = data.get("refresh_token", refresh_token)
        expires_in = data.get("expires_in", 3600)

        # Save new credentials — preserve existing fields (scopes, clientId, etc.)
        creds = json.loads(CREDENTIALS_PATH.read_text())
        existing_oauth = creds.get("claudeAiOauth", {})
        existing_oauth["accessToken"] = new_token
        existing_oauth["refreshToken"] = new_refresh
        existing_oauth["expiresAt"] = int(time.time() * 1000) + expires_in * 1000
        creds["claudeAiOauth"] = existing_oauth
        CREDENTIALS_PATH.write_text(json.dumps(creds, indent=2))
        # v4.11.2026.1 security fix (P2-9): chmod 0600 after write so a
        # fresh file inherits the same permissions that config.py's
        # _save_secrets applies. Inherited umask on a shared system
        # could otherwise leave credentials world-readable.
        try:
            os.chmod(CREDENTIALS_PATH, 0o600)
        except OSError as exc:
            logger.debug("chmod 0600 on credentials failed: %s", exc)

        # Also update secrets.json if it has the old token
        from clawed.paths import data_dir
        secrets_path = data_dir() / "secrets.json"
        if secrets_path.exists():
            try:
                secrets = json.loads(secrets_path.read_text())
                if secrets.get("anthropic_api_key", "").startswith("sk-ant-oat"):
                    secrets["anthropic_api_key"] = new_token
                    secrets_path.write_text(json.dumps(secrets, indent=2))
                    try:
                        os.chmod(secrets_path, 0o600)
                    except OSError as exc:
                        logger.debug("chmod 0600 on secrets.json failed: %s", exc)
            except (json.JSONDecodeError, OSError):
                pass

        logger.info("OAuth token refreshed, expires in %ds", expires_in)
        return new_token

    except Exception as e:
        logger.warning("Token refresh error: %s", e)
        return None
