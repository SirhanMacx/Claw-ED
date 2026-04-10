#!/usr/bin/env python3
"""OAuth login for Claw-ED — generates an independent token per machine.

Usage:
    python3 scripts/oauth_login.py

Opens a browser URL for you to authorize. Paste the code back.
Saves credentials to ~/.claude/.credentials.json
"""

import json
import os
import secrets
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import httpx

CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
AUTHORIZE_URL = "https://claude.com/cai/oauth/authorize"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
REDIRECT_URL = "https://platform.claude.com/oauth/code/callback"
SCOPES = "user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload"

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"


def main():
    # Generate PKCE code verifier/challenge
    code_verifier = secrets.token_urlsafe(64)
    import base64
    import hashlib

    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()

    state = secrets.token_urlsafe(32)

    # Build authorization URL
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URL,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"

    print("\n  Claw-ED OAuth Login")
    print("  ===================\n")
    print("  Open this URL in your browser:\n")
    print(f"  {auth_url}\n")

    try:
        webbrowser.open(auth_url)
        print("  (Browser should open automatically)\n")
    except Exception:
        print("  (Copy the URL above and open it manually)\n")

    print("  After authorizing, you'll see a code. Paste it here:\n")
    auth_code = input("  Code: ").strip()

    if not auth_code:
        print("  No code entered. Aborting.")
        sys.exit(1)

    # Exchange code for tokens
    print("\n  Exchanging code for tokens...")
    resp = httpx.post(
        TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URL,
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/json"},
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"  Error: {resp.status_code} — {resp.text[:200]}")
        sys.exit(1)

    data = resp.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token", "")
    expires_in = data.get("expires_in", 28800)

    # Save credentials
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    creds = {
        "claudeAiOauth": {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expiresAt": int(time.time() * 1000) + expires_in * 1000,
        }
    }
    CREDENTIALS_PATH.write_text(json.dumps(creds, indent=2))
    os.chmod(str(CREDENTIALS_PATH), 0o600)

    # Also save to Claw-ED secrets
    secrets_path = Path.home() / ".eduagent" / "secrets.json"
    try:
        s = json.loads(secrets_path.read_text()) if secrets_path.exists() else {}
        s["anthropic_api_key"] = access_token
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.write_text(json.dumps(s, indent=2))
        os.chmod(str(secrets_path), 0o600)
    except Exception:
        pass

    print(f"\n  Token saved to {CREDENTIALS_PATH}")
    print(f"  Token prefix: {access_token[:20]}...")
    print(f"  Expires in: {expires_in // 3600}h")

    # Quick test
    print("\n  Testing API access...")
    test = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "x-app": "cli",
            "Content-Type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": "Say OK"}],
        },
        timeout=15,
    )

    if test.status_code == 200:
        print(f"  API works! Response: {test.json()['content'][0]['text']}")
    else:
        print(f"  API test: {test.status_code}")

    print("\n  Done! Run 'clawed lesson \"Topic\"' to generate.\n")


if __name__ == "__main__":
    main()
