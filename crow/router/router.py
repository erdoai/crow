"""Routes inbound messages to agents and creates jobs."""

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
        """Route message to the requested, current, or default (PA) agent."""
        gateway = event.data["gateway"]
        gateway_thread_id = event.data["gateway_thread_id"]
        text = event.data["text"]

        # Get or create conversation for this gateway thread
        user_id = event.data.get("user_id")
        conversation = await self.db.get_or_create_conversation(
            gateway=gateway,
            gateway_thread_id=gateway_thread_id,
            user_id=user_id,
        )

        # Save inbound message
        msg_id = await self.db.insert_message(
            conversation_id=conversation["id"],
            role="user",
            content=text,
        )

        # Save any file attachments
        for att in event.data.get("attachments") or []:
            await self.db.insert_attachment(
                message_id=msg_id,
                filename=att["filename"],
                content_type=att["content_type"],
                size_bytes=att["size_bytes"],
                data=att["data"],
            )

        # Route to specific agent if requested, continue with the
        # conversation's current agent, or fall back to PA.
        agent_name = event.data.get("agent")
        if not agent_name:
            agent_name = await self.db.last_agent_for_conversation(
                conversation["id"]
            ) or "pa"

        # Resolve job mode: explicit request > agent default > chat
        mode = event.data.get("mode")
        if not mode:
            agent_def = await self.db.get_agent_def(
                agent_name, user_id=user_id
            )
            mode = agent_def.get("mode", "chat") if agent_def else "chat"

        job_id = await self.db.create_job(
            agent_name=agent_name,
            input_text=text,
            conversation_id=conversation["id"],
            mode=mode,
        )

        logger.info(
            "Routed message to %s agent: job=%s conversation=%s",
            agent_name,
            job_id,
            conversation["id"],
        )

        await self.bus.publish(
            Event(
                type=JOB_CREATED,
                data={
                    "job_id": job_id,
                    "agent_name": agent_name,
                    "conversation_id": conversation["id"],
                    "text": text,
                },
            )
        )
