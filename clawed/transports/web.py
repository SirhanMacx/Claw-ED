"""Web transport for Claw-ED — FastAPI-based dashboard and API.

The web transport is more complex than other transports (templates, static files,
multiple route modules), so it lives in clawed/api/. This module provides a
convenience import path.

Usage:
    from clawed.transports.web import create_app
    app = create_app()
"""
from clawed.api.server import create_app

__all__ = ["create_app"]
