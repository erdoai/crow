"""Routes inbound messages through the PA agent to create jobs."""

import logging

from crow.db.database import Database
from crow.events.bus import EventBus
from crow.events.types import JOB_CREATED, MESSAGE_INBOUND, Event

logger = logging.getLogger(__name__)


class Router:
    def __init__(self, bus: EventBus, db: Database):
        self.bus = bus
        self.db = db
        bus.subscribe(MESSAGE_INBOUND, self.route)

    async def route(self, event: Event) -> None:
        """All inbound messages go to the PA agent, which decides what to do."""
        gateway = event.data["gateway"]
        gateway_thread_id = event.data["gateway_thread_id"]
        text = event.data["text"]

        # Get or create conversation for this gateway thread
        conversation = await self.db.get_or_create_conversation(
            gateway=gateway,
            gateway_thread_id=gateway_thread_id,
        )

        # Save inbound message
        await self.db.insert_message(
            conversation_id=conversation["id"],
            role="user",
            content=text,
        )

        # Create a job for the PA agent — it will decide how to route
        job_id = await self.db.create_job(
            agent_name="pa",
            input_text=text,
            conversation_id=conversation["id"],
        )

        logger.info(
            "Routed message to PA agent: job=%s conversation=%s",
            job_id,
            conversation["id"],
        )

        await self.bus.publish(
            Event(
                type=JOB_CREATED,
                data={
                    "job_id": job_id,
                    "agent_name": "pa",
                    "conversation_id": conversation["id"],
                    "text": text,
                },
            )
        )
