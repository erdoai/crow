"""Zombie job reaper — requeues stuck jobs for resume, or fails them.

Jobs stuck in 'running' with no checkpoint update for TIMEOUT_MINUTES
are presumed dead (worker crashed, deploy, network partition).
Jobs under MAX_ATTEMPTS are requeued (preserving checkpoint) so a new
worker can resume. Jobs at the cap are permanently failed.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from crow.events.types import JOB_FAILED, Event

logger = logging.getLogger(__name__)

TIMEOUT_MINUTES = 10
POLL_INTERVAL = 60  # check every minute
MAX_ATTEMPTS = 3


async def reaper_loop(db, bus) -> None:
    """Background task that requeues or fails zombie jobs."""
    logger.info(
        "Job reaper started (timeout=%dm, poll=%ds, max_attempts=%d)",
        TIMEOUT_MINUTES,
        POLL_INTERVAL,
        MAX_ATTEMPTS,
    )
    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)
            cutoff = datetime.now(UTC) - timedelta(minutes=TIMEOUT_MINUTES)
            requeued, failed = await db.requeue_zombie_jobs(
                cutoff, MAX_ATTEMPTS
            )
            for job in requeued:
                logger.info(
                    "Requeued zombie job %s (agent=%s, attempt=%d)",
                    job["id"],
                    job["agent_name"],
                    job["attempt"],
                )
            for job in failed:
                logger.warning(
                    "Permanently failed job %s after %d attempts (agent=%s)",
                    job["id"],
                    job["attempt"],
                    job["agent_name"],
                )
                await bus.publish(Event(
                    type=JOB_FAILED,
                    data={
                        "job_id": job["id"],
                        "error": (
                            f"Job failed after {job['attempt']} attempts "
                            f"(no worker heartbeat for {TIMEOUT_MINUTES}m)"
                        ),
                    },
                ))
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Reaper error")
