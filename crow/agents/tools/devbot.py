"""Tools for querying devbot API."""

import httpx

from crow.agents.tools import tool_def

LIST_JOBS_DEF = tool_def(
    name="devbot.list_jobs",
    description="List recent devbot jobs. Returns job ID, status, prompt, and timestamps.",
    parameters={
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter by status. Omit for all.",
                "enum": ["pending", "running", "success", "failed"],
            },
            "limit": {
                "type": "integer",
                "description": "Max number of jobs to return (default 10)",
            },
        },
        "required": [],
    },
)

GET_JOB_DEF = tool_def(
    name="devbot.get_job",
    description="Get details of a specific devbot job by ID.",
    parameters={
        "properties": {
            "job_id": {
                "type": "string",
                "description": "The devbot job ID",
            },
        },
        "required": ["job_id"],
    },
)

CREATE_JOB_DEF = tool_def(
    name="devbot.create_job",
    description="Create a devbot job. Autonomously implements the prompt as a PR.",
    parameters={
        "properties": {
            "prompt": {
                "type": "string",
                "description": "What to implement",
            },
            "repo": {
                "type": "string",
                "description": "Repository (org/repo format)",
            },
        },
        "required": ["prompt", "repo"],
    },
)


async def list_jobs(devbot_url: str, status: str | None = None, limit: int = 10) -> str:
    try:
        async with httpx.AsyncClient() as client:
            params: dict = {"limit": limit}
            if status:
                params["status"] = status
            resp = await client.get(f"{devbot_url}/api/jobs", params=params, timeout=10)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        return f"Error querying devbot: {e}"


async def get_job(devbot_url: str, job_id: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{devbot_url}/api/jobs/{job_id}", timeout=10)
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        return f"Error querying devbot: {e}"


async def create_job(devbot_url: str, prompt: str, repo: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{devbot_url}/api/jobs",
                json={"prompt": prompt, "repo": repo, "job_type": "impl"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.text
    except Exception as e:
        return f"Error creating devbot job: {e}"
