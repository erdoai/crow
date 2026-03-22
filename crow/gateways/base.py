from abc import ABC, abstractmethod

from crow.events.bus import EventBus


class Gateway(ABC):
    """Abstract gateway — receives messages from external systems, delivers responses."""

    name: str

    @abstractmethod
    async def start(self, bus: EventBus) -> None:
        """Start listening. Publish message.inbound events to the bus."""

    @abstractmethod
    async def stop(self) -> None:
        """Clean shutdown."""

    @abstractmethod
    async def send(self, gateway_thread_id: str, text: str) -> None:
        """Send a response back to the user."""
