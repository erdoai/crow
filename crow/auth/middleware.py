"""Auth middleware — enforces authentication on all routes by default.

Routes must be explicitly allowlisted to be public. Worker routes that
present a valid x-worker-key are authenticated here in the middleware.
"""

import logging
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

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
)

# Path prefixes that accept worker-key authentication.
# The middleware validates the key centrally; handlers don't need to.
WORKER_KEY_PREFIXES: tuple[str, ...] = (
    "/workers/",
    "/jobs/",
    "/agents/",
    "/scheduled-jobs/",
)


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        path = request.url.path

        # Public routes — no auth needed
        if _is_public(path):
            return await call_next(request)

        # Worker-key authentication — validate centrally
        worker_key = request.headers.get("x-worker-key")
        if worker_key and any(path.startswith(p) for p in WORKER_KEY_PREFIXES):
            expected = request.app.state.settings.worker_api_key
            if worker_key == expected:
                return await call_next(request)
            return JSONResponse(
                {"detail": "Invalid worker key"}, status_code=401
            )

        # Everything else requires user auth
        user = await get_current_user(request)
        if user:
            # Attach user + scoping ID to request state for downstream handlers
            request.state.user = user
            # user_id for DB scoping: None = instance-level (static API key / default user)
            request.state.user_id = user["id"] if user.get("id") != "default" else None
            return await call_next(request)

        # Not authenticated — decide response format
        if request.headers.get("authorization", "").startswith("Bearer "):
            return JSONResponse(
                {"detail": "Invalid API key"}, status_code=401
            )

        # Unauthenticated HTML requests → redirect to login
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/login", status_code=303)

        return JSONResponse(
            {"detail": "Authentication required"}, status_code=401
        )
