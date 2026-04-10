"""Google Gemini authentication — API key.

Resolution order:
1. Environment variables (GOOGLE_API_KEY / GEMINI_API_KEY)
2. OS keyring (stored by setup wizard)
3. Secrets file fallback

OAuth2 browser flow is planned but requires a registered Google Cloud
client ID. To enable it:
1. Create a project at https://console.cloud.google.com
2. Enable the Generative Language API
3. Create OAuth 2.0 credentials (Desktop app type)
4. Set GOOGLE_CLIENT_ID env var to your client ID
5. The run_google_oauth_flow() function will then work

For now, API key auth works perfectly:
  Get a free key at https://aistudio.google.com/apikey
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_google_api_key() -> str | None:
    """Resolve Google API key from env, keyring, or config."""
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        from clawed.config import get_api_key

        stored = get_api_key("google")
        if stored:
            return stored
    except Exception:
        pass
    return None


def has_google_credentials() -> bool:
    """Check if Google credentials are available."""
    return get_google_api_key() is not None
