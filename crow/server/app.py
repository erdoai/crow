"""FastAPI application with lifespan."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from crow.auth.middleware import AuthMiddleware
from crow.config.loader import auto_import_if_empty, extract_auth_config, load_config
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
    stream,
    workers,
)

logger = logging.getLogger(__name__)

# Path to the built React SPA
SPA_DIR = Path(__file__).parent.parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings

    # Load crow.yml and extract auth config
    crow_config = load_config()
    app.state.auth_config = extract_auth_config(crow_config)

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

    # Legacy static files (templates CSS/JS)
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # SPA static assets (Vite build output)
    if (SPA_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=SPA_DIR / "assets"), name="spa-assets")

    # API routes
    app.include_router(health.router)
    app.include_router(messages.router)
    app.include_router(agents.router)
    app.include_router(conversations.router)
    app.include_router(stream.router)
    app.include_router(jobs.router)
    app.include_router(workers.router)
    app.include_router(config.router)

    # Auth + dashboard
    app.include_router(auth.api_router)  # /api/me
    app.include_router(auth.router)      # /auth/*
    app.include_router(dashboard.router)

    # SPA catch-all — serves index.html for all non-API routes
    if SPA_DIR.exists():
        @app.get("/{full_path:path}")
        async def spa_catch_all(request: Request, full_path: str):
            # If the path matches a file in dist/, serve it directly
            file_path = SPA_DIR / full_path
            if full_path and file_path.is_file():
                return FileResponse(file_path)
            # Otherwise serve index.html for client-side routing
            return FileResponse(SPA_DIR / "index.html")

    # Auth middleware — enforces authentication on all routes not in the allowlist
    app.add_middleware(AuthMiddleware)

    return app
