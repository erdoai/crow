"""Worker loop — polls server for jobs, executes them, reports results."""

import asyncio
import logging
import platform
import signal
from uuid import uuid4

import httpx

from crow.config.settings import Settings
from crow.worker.executor import SHUTDOWN_SENTINEL, run_agent

logger = logging.getLogger(__name__)


async def worker_loop(server_url: str, settings: Settings) -> None:
    """Main worker loop. Polls server for jobs and executes them."""
    worker_id = uuid4().hex[:12]
    worker_name = platform.node()
    headers = {
        "x-worker-key": settings.worker_api_key,
        "x-worker-id": worker_id,
    }

    shutdown_requested = False

    def _request_shutdown():
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info("Shutdown signal received, finishing current work...")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for SIGTERM
            pass

    async with httpx.AsyncClient(timeout=30) as client:
        # Register
        await client.post(
            f"{server_url}/workers/register",
            headers=headers,
            json={"worker_id": worker_id, "name": worker_name},
        )
        logger.info("Worker %s (%s) registered with %s", worker_id, worker_name, server_url)

        while not shutdown_requested:
            try:
                # Poll for next job
                resp = await client.get(f"{server_url}/jobs/next/claim", headers=headers)
                resp.raise_for_status()

                job_data = resp.json()
                if not job_data:
                    # No jobs available — heartbeat and wait
                    await client.post(f"{server_url}/workers/heartbeat", headers=headers)
                    await asyncio.sleep(2)
                    continue

                job = job_data["job"]
                logger.info(
                    "Claimed job %s (agent=%s, attempt=%d): %s",
                    job["id"],
                    job["agent_name"],
                    job.get("attempt", 0),
                    job["input"][:80],
                )

                # Execute
                try:
                    output, tokens = await run_agent(
                        job_data, settings, server_url, settings.worker_api_key,
                        should_stop=lambda: shutdown_requested,
                    )

                    # On graceful shutdown, requeue for another worker
                    if output == SHUTDOWN_SENTINEL:
                        logger.info(
                            "Requeueing job %s for resume, exiting",
                            job["id"],
                        )
                        await client.post(
                            f"{server_url}/jobs/{job['id']}/requeue",
                            headers=headers,
                        )
                        break

                    await client.post(
                        f"{server_url}/jobs/{job['id']}/result",
                        headers=headers,
                        json={"output": output, "tokens_used": tokens},
                    )
                    logger.info("Job %s completed (%d tokens)", job["id"], tokens)
                except Exception as e:
                    logger.exception("Job %s failed", job["id"])
                    await client.post(
                        f"{server_url}/jobs/{job['id']}/error",
                        headers=headers,
                        json={"error": str(e)},
                    )

            except httpx.HTTPError:
                logger.warning("Failed to reach server at %s, retrying...", server_url)
                await asyncio.sleep(5)
            except Exception:
                logger.exception("Worker loop error")
                await asyncio.sleep(5)

    logger.info("Worker %s shutting down", worker_id)
