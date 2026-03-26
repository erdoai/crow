"""Scheduler loop — promotes due scheduled jobs to pending jobs."""

import asyncio
import logging
from datetime import UTC, datetime

from croniter import croniter

from crow.db.database import Database
from crow.events.bus import EventBus
from crow.events.types import JOB_CREATED, Event

logger = logging.getLogger(__name__)

POLL_INTERVAL = 10  # seconds


async def scheduler_loop(db: Database, bus: EventBus) -> None:
    """Check for due scheduled jobs every POLL_INTERVAL seconds."""
    logger.info("Scheduler started (poll every %ds)", POLL_INTERVAL)
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            due = await db.get_due_scheduled_jobs()
            for sj in due:
                job_id = await db.create_job(
                    agent_name=sj["agent_name"],
                    input_text=sj["input"],
                    conversation_id=sj.get("conversation_id"),
                    source="schedule",
                )
                await bus.publish(Event(
                    type=JOB_CREATED,
                    data={
                        "job_id": job_id,
                        "agent_name": sj["agent_name"],
                        "conversation_id": sj.get("conversation_id"),
                        "text": sj["input"],
                        "scheduled_job_id": sj["id"],
                    },
                ))
                logger.info(
                    "Scheduled job %s fired → job %s (agent=%s)",
                    sj["id"], job_id, sj["agent_name"],
                )

                # Advance: compute next run for cron, or complete for one-shot
                if sj.get("cron"):
                    next_run = croniter(
                        sj["cron"], datetime.now(UTC)
                    ).get_next(datetime)
                    await db.advance_scheduled_job(sj["id"], next_run_at=next_run)
                else:
                    await db.advance_scheduled_job(sj["id"], next_run_at=None)
        except Exception:
            logger.exception("Scheduler loop error")
