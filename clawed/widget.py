"""Shared, escaped embed markup for the dashboard and CLI."""

from html import escape


def build_embed_snippet(base_url: str, lesson_id: str, share_token: str) -> str:
    base = base_url.rstrip("/")
    attrs = {
        "src": f"{base}/static/widget.js",
        "data-api-url": base,
        "data-lesson-id": lesson_id,
        "data-share-token": share_token,
    }
    attributes = " ".join(f'{key}="{escape(value, quote=True)}"' for key, value in attrs.items())
    return f"<script {attributes} defer></script>"
