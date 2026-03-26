"""Zombie job reaper — marks stuck jobs as failed.

Jobs stuck in 'running' with no worker heartbeat for TIMEOUT_MINUTES
are presumed dead (worker crashed, network partition, etc.).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from crow.events.types import JOB_FAILED, Event

logger = logging.getLogger(__name__)

TIMEOUT_MINUTES = 10
POLL_INTERVAL = 60  # check every minute


async def reaper_loop(db, bus) -> None:
    """Background task that reaps zombie jobs."""
    logger.info(
        "Job reaper started (timeout=%dm, poll=%ds)",
        TIMEOUT_MINUTES,
        POLL_INTERVAL,
    )
    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)
            cutoff = datetime.now(UTC) - timedelta(minutes=TIMEOUT_MINUTES)
            reaped = await db.reap_zombie_jobs(cutoff)
            for job in reaped:
                logger.warning(
                    "Reaped zombie job %s (agent=%s, started=%s)",
                    job["id"],
                    job["agent_name"],
                    job.get("started_at"),
                )
                await bus.publish(Event(
                    type=JOB_FAILED,
                    data={
                        "job_id": job["id"],
                        "error": (
                            f"Job timed out after {TIMEOUT_MINUTES}m "
                            f"with no worker heartbeat"
                        ),
                    },
                ))
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Reaper error")
