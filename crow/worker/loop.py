"""Worker loop — polls server for jobs, executes them, reports results."""

import asyncio
import logging
import platform
from uuid import uuid4

import httpx

from crow.config.settings import Settings
from crow.worker.executor import run_agent

logger = logging.getLogger(__name__)


async def worker_loop(server_url: str, settings: Settings) -> None:
    """Main worker loop. Polls server for jobs and executes them."""
    worker_id = uuid4().hex[:12]
    worker_name = platform.node()
    headers = {
        "x-worker-key": settings.worker_api_key,
        "x-worker-id": worker_id,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # Register
        await client.post(
            f"{server_url}/workers/register",
            headers=headers,
            json={"worker_id": worker_id, "name": worker_name},
        )
        logger.info("Worker %s (%s) registered with %s", worker_id, worker_name, server_url)

        while True:
            try:
                # Poll for next job
                resp = await client.get(f"{server_url}/jobs/next", headers=headers)
                resp.raise_for_status()

                job_data = resp.json()
                if not job_data:
                    # No jobs available — heartbeat and wait
                    await client.post(f"{server_url}/workers/heartbeat", headers=headers)
                    await asyncio.sleep(2)
                    continue

                job = job_data["job"]
                logger.info(
                    "Claimed job %s (agent=%s): %s",
                    job["id"],
                    job["agent_name"],
                    job["input"][:80],
                )

                # Execute
                try:
                    output, tokens = await run_agent(
                        job_data, settings, server_url, settings.worker_api_key
                    )
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
