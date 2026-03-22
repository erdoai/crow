import asyncio
import fnmatch
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from crow.events.types import Event

logger = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Subscribe to an event type. Supports wildcards like 'message.*'."""
        self._subscribers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers."""
        for pattern, handlers in self._subscribers.items():
            if pattern == event.type or fnmatch.fnmatch(event.type, pattern):
                for handler in handlers:
                    asyncio.create_task(self._safe_call(handler, event))

    async def _safe_call(self, handler: Handler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception("Event handler failed for %s", event.type)
