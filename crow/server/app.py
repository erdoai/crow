"""FastAPI application with lifespan."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from crow.config.loader import auto_import_if_empty, extract_auth_config, load_config
from crow.config.settings import Settings
from crow.db.database import Database
from crow.events.bus import EventBus
from crow.gateways.api.gateway import APIGateway
from crow.gateways.imessage.gateway import IMessageGateway
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

    if settings.imessage_enabled:
        imsg_gw = IMessageGateway(settings, db)
        await imsg_gw.start(bus)
        gateways.append(imsg_gw)
        logger.info("iMessage gateway enabled")

    logger.info("crow server started on %s:%d", settings.host, settings.port)

    yield

    for gw in gateways:
        await gw.stop()
    await db.close()
    logger.info("crow server stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="crow", lifespan=lifespan)

    # Static files
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

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
    app.include_router(auth.router)
    app.include_router(dashboard.router)

    return app
