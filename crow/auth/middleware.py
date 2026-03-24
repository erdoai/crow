"""Auth middleware — enforces authentication on all routes by default.

Routes must be explicitly allowlisted to be public. Worker routes that
use x-worker-key are also allowlisted (they enforce their own auth).
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

# Path prefixes where routes enforce their own auth via x-worker-key.
# The middleware lets them through; the route handler validates the key.
WORKER_KEY_PREFIXES: tuple[str, ...] = (
    "/workers/",
    "/jobs/",
)

# Specific paths that use x-worker-key (not covered by prefixes above).
WORKER_KEY_PATHS: set[str] = set()

# Path patterns where POST uses x-worker-key but GET is user-facing.
# POST to these paths is allowed through if x-worker-key header is present.
WORKER_KEY_POST_PREFIXES: tuple[str, ...] = (
    "/agents/",
)


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def _is_worker_authed(request: Request) -> bool:
    """Check if the request is to a worker-key-protected route."""
    path = request.url.path
    if path in WORKER_KEY_PATHS:
        return True
    if any(path.startswith(p) for p in WORKER_KEY_PREFIXES):
        return True
    # POST/PUT to agent routes with x-worker-key header
    if request.method in ("POST", "PUT") and any(
        path.startswith(p) for p in WORKER_KEY_POST_PREFIXES
    ):
        return "x-worker-key" in request.headers
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        path = request.url.path

        # Public routes — no auth needed
        if _is_public(path):
            return await call_next(request)

        # Worker-key routes — they enforce their own auth
        if _is_worker_authed(request):
            return await call_next(request)

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
