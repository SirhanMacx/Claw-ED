"""CORS for the public student widget, isolated from teacher routes."""

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class StudentWidgetCORS:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.student_app = CORSMiddleware(
            app, allow_origins=["*"], allow_methods=["POST"],
            allow_headers=["Content-Type"], allow_credentials=False,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = self.student_app if scope["type"] == "http" and scope["path"] == "/api/chat/student" else self.app
        await app(scope, receive, send)
