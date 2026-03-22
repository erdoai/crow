"""FastAPI application with lifespan — starts DB, event bus, gateways, router."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from crow.agents.definitions.monitor import monitor
from crow.agents.definitions.pa import pa
from crow.agents.definitions.planner import planner
from crow.agents.definitions.reviewer import reviewer
from crow.agents.registry import AgentRegistry
from crow.config.settings import Settings
from crow.db.database import Database
from crow.events.bus import EventBus
from crow.gateways.api.gateway import APIGateway
from crow.gateways.imessage.gateway import IMessageGateway
from crow.router.router import Router
from crow.server.routes import agents, conversations, health, jobs, messages, workers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.settings = settings

    # Database
    db = await Database.connect(settings.database_url)
    app.state.db = db

    # Event bus
    bus = EventBus()
    app.state.bus = bus

    # Agent registry
    registry = AgentRegistry()
    registry.register(pa)
    registry.register(monitor)
    registry.register(planner)
    registry.register(reviewer)
    app.state.registry = registry

    # Router (subscribes to message.inbound)
    _router = Router(bus, db)

    # Gateways
    gateways = []

    api_gw = APIGateway()
    await api_gw.start(bus)
    gateways.append(api_gw)
    app.state.api_gateway = api_gw

    if settings.imessage_enabled:
        imsg_gw = IMessageGateway(settings)
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
    app.include_router(health.router)
    app.include_router(messages.router)
    app.include_router(agents.router)
    app.include_router(conversations.router)
    app.include_router(jobs.router)
    app.include_router(workers.router)
    return app
