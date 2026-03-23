"""FastAPI application with lifespan."""

import base64
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from crow.auth.middleware import AuthMiddleware
from crow.config.loader import (
    auto_import_if_empty,
    extract_auth_config,
    extract_dashboard_config,
    load_config,
)
from crow.config.settings import Settings
from crow.db.database import Database
from crow.events.bus import EventBus
from crow.gateways.api.gateway import APIGateway
from crow.router.router import Router
from crow.server.routes import (
    agents,
    auth,
    config,
    conversations,
    dashboard,
    health,
    jobs,
    messages,
    state,
    stream,
    workers,
)

logger = logging.getLogger(__name__)

# Path to the built React SPA — resolve from cwd (Docker WORKDIR=/app)
# rather than __file__ which points to site-packages when pip-installed.
SPA_DIR = Path.cwd() / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings

    # Load crow.yml and extract auth config
    crow_config = load_config()
    app.state.auth_config = extract_auth_config(crow_config)
    app.state.dashboard_config = extract_dashboard_config(crow_config)

    # Database
    db = await Database.connect(settings.database_url)
    app.state.db = db

    # Auto-import crow.yml if DB has no agents
    await auto_import_if_empty(db)

    # Event bus
    bus = EventBus()
    app.state.bus = bus

    # Router (subscribes to message.inbound)
    _router = Router(bus, db)

    # Gateways
    gateways = []

    api_gw = APIGateway()
    await api_gw.start(bus)
    gateways.append(api_gw)
    app.state.api_gateway = api_gw

    logger.info("crow server started on %s:%d", settings.host, settings.port)

    yield

    for gw in gateways:
        await gw.stop()
    await db.close()
    logger.info("crow server stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="crow", lifespan=lifespan)

    # SPA static assets (Vite build output)
    if (SPA_DIR / "assets").exists():
        app.mount(
            "/assets",
            StaticFiles(directory=SPA_DIR / "assets"),
            name="spa-assets",
        )

    # API routes
    app.include_router(health.router)
    app.include_router(messages.router)
    app.include_router(agents.router)
    app.include_router(conversations.router)
    app.include_router(stream.router)
    app.include_router(jobs.router)
    app.include_router(workers.router)
    app.include_router(config.router)
    app.include_router(state.router)

    # Auth + dashboard JSON APIs
    app.include_router(auth.api_router)  # /api/me
    app.include_router(auth.router)      # /auth/*
    app.include_router(dashboard.router)

    # Custom dashboard views (static HTML dirs from crow.yml)
    crow_config = load_config()
    for view_name, view_cfg in extract_dashboard_config(crow_config).get("views", {}).items():
        view_path = Path(view_cfg["path"])
        if view_path.is_dir():
            app.mount(
                f"/dashboard/custom/{view_name}",
                StaticFiles(directory=view_path, html=True),
                name=f"custom-{view_name}",
            )

    # DB-stored custom dashboard views — serves files from the database
    @app.get("/dashboard/custom/{name}/{path:path}")
    async def serve_db_dashboard(name: str, path: str, request: Request):
        """Serve dashboard files from DB. Falls back to file-based mounts."""
        db = request.app.state.db
        view = await db.get_dashboard_view(name)
        if not view:
            # Not in DB — let file-based StaticFiles mount handle it (or 404)
            from fastapi.responses import HTMLResponse
            return HTMLResponse(status_code=404, content="Not found")

        import json
        files = view["files"] if isinstance(view["files"], dict) else json.loads(view["files"])
        file_path = path or "index.html"
        if not file_path or file_path.endswith("/"):
            file_path = (file_path or "") + "index.html"

        content_b64 = files.get(file_path)
        if not content_b64:
            return Response(status_code=404, content="File not found")

        content = base64.b64decode(content_b64)
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"
        return Response(content=content, media_type=mime_type)

    # SPA catch-all — serves index.html for all non-API routes
    if SPA_DIR.exists():
        @app.get("/{full_path:path}")
        async def spa_catch_all(request: Request, full_path: str):
            file_path = SPA_DIR / full_path
            if full_path and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(SPA_DIR / "index.html")

    # Auth middleware
    app.add_middleware(AuthMiddleware)

    return app
