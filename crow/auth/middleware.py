"""Auth middleware — enforces authentication on all routes by default.

Uses raw ASGI middleware (not BaseHTTPMiddleware) to properly handle
both HTTP requests and WebSocket connections.
"""

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from crow.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

# Paths that require no authentication at all.
PUBLIC_PATHS: set[str] = {
    "/healthz",
    "/auth/send-code",
    "/auth/verify",
    "/auth/verify-passphrase",
    "/auth/gate-status",
    "/auth/logout",
    "/login",
    "/",
    "/api/me",
}

# Path prefixes that are always public.
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/assets/",
    "/shared/",
    "/api/shared/",
    "/ws",  # WebSocket — auth via ephemeral token in handler
)

# Path prefixes that accept worker-key authentication.
WORKER_KEY_PREFIXES: tuple[str, ...] = (
    "/workers",
    "/jobs",
    "/agents",
    "/scheduled-jobs",
    "/api/store",
)


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class AuthMiddleware:
    """ASGI middleware that enforces auth on HTTP, passes WebSocket through."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        # WebSocket connections: pass through (auth in handler)
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        # Non-HTTP (lifespan etc): pass through
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive, send)
        path = request.url.path.rstrip("/") or "/"

        # Public routes — no auth needed
        if _is_public(path):
            await self.app(scope, receive, send)
            return

        # Worker-key authentication
        worker_key = request.headers.get("x-worker-key")
        if worker_key and any(
            path.startswith(p) for p in WORKER_KEY_PREFIXES
        ):
            expected = request.app.state.settings.worker_api_key
            if worker_key == expected:
                await self.app(scope, receive, send)
                return
            response = JSONResponse(
                {"detail": "Invalid worker key"}, status_code=401
            )
            await response(scope, receive, send)
            return

        # User auth
        user = await get_current_user(request)
        if user:
            scope.setdefault("state", {})
            scope["state"]["user"] = user
            scope["state"]["user_id"] = (
                user["id"] if user.get("id") != "default" else None
            )
            await self.app(scope, receive, send)
            return

        # Not authenticated
        if request.headers.get("authorization", "").startswith("Bearer "):
            response = JSONResponse(
                {"detail": "Invalid API key"}, status_code=401
            )
            await response(scope, receive, send)
            return

        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            response = RedirectResponse(url="/login", status_code=303)
            await response(scope, receive, send)
            return

        response = JSONResponse(
            {"detail": "Authentication required"}, status_code=401
        )
        await response(scope, receive, send)
