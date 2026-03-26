"""HTTP API gateway — receives messages via POST /messages."""

import logging

from crow.events.bus import EventBus
from crow.events.types import MESSAGE_INBOUND, Event
from crow.gateways.base import Gateway

logger = logging.getLogger(__name__)


class APIGateway(Gateway):
    name = "api"

    def __init__(self):
        self._bus: EventBus | None = None

    async def start(self, bus: EventBus) -> None:
        self._bus = bus

    async def stop(self) -> None:
        pass

    async def send(self, gateway_thread_id: str, text: str) -> None:
        # API gateway doesn't push responses — callers poll or use SSE
        pass

    async def handle_inbound(
        self,
        gateway_thread_id: str,
        text: str,
        agent: str | None = None,
        user_id: str | None = None,
        attachments: list[dict] | None = None,
        mode: str = "chat",
    ) -> None:
        """Called by the FastAPI route."""
        if not self._bus:
            return
        data: dict = {
            "gateway": "api",
            "gateway_thread_id": gateway_thread_id,
            "text": text,
            "user_id": user_id,
        }
        if agent:
            data["agent"] = agent
        if attachments:
            data["attachments"] = attachments
        if mode != "chat":
            data["mode"] = mode
        await self._bus.publish(Event(type=MESSAGE_INBOUND, data=data))
