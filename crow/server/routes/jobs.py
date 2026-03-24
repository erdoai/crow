"""Job queue endpoints — public listing + worker-facing claim/result."""

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from crow.auth.dependencies import get_current_user
from crow.events.types import MESSAGE_RESPONSE, Event

router = APIRouter(prefix="/jobs")


def _check_worker_key(request: Request, x_worker_key: str = Header()) -> None:
    expected = request.app.state.settings.worker_api_key
    if x_worker_key != expected:
        raise HTTPException(status_code=401, detail="Invalid worker key")


def _user_id_from_request(request, user):
    auth_enabled = request.app.state.auth_config.get("enabled", True)
    if auth_enabled and user and user["id"] != "default":
        return user["id"]
    return None


# -- Public --


@router.get("")
async def list_jobs(
    request: Request,
    status: str | None = None,
    limit: int = 50,
):
    """List recent jobs."""
    user = await get_current_user(request)
    uid = _user_id_from_request(request, user)
    db = request.app.state.db
    return await db.list_jobs(status=status, limit=limit, user_id=uid)


@router.get("/{job_id}")
async def get_job(job_id: str, request: Request):
    """Get a specific job."""
    user = await get_current_user(request)
    uid = _user_id_from_request(request, user)
    db = request.app.state.db
    job = await db.get_job(job_id, user_id=uid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# -- Worker-facing --


@router.get("/next/claim")
async def claim_next_job(request: Request, x_worker_key: str = Header()):
    """Worker claims the next pending job."""
    _check_worker_key(request, x_worker_key)
    worker_id = request.headers.get("x-worker-id", "unknown")

    db = request.app.state.db
    job = await db.claim_next_job(worker_id)
    if not job:
        return None

    # Load agent definition from DB (scoped to the user who created the conversation)
    job_user_id = None
    if job.get("conversation_id"):
        conv = await db.get_conversation(job["conversation_id"])
        if conv:
            job_user_id = conv.get("user_id")
    agent_def = await db.get_agent_def(job["agent_name"], user_id=job_user_id)

    # Load conversation history
    messages = []
    if job["conversation_id"]:
        messages = await db.get_messages(job["conversation_id"])

    # Load relevant knowledge
    knowledge = []
    if agent_def and agent_def.get("knowledge_areas"):
        knowledge = await db.search_knowledge(
            agent_name=job["agent_name"],
            limit=20,
        )

    # Load MCP server configs — agent-level inline configs override instance-level
    mcp_servers = []
    if agent_def:
        # 1. Inline MCP configs from agent (highest priority)
        agent_mcp_configs = agent_def.get("mcp_configs")
        if agent_mcp_configs:
            import json as _json
            if isinstance(agent_mcp_configs, str):
                agent_mcp_configs = _json.loads(agent_mcp_configs)
            for name, config in agent_mcp_configs.items():
                mcp_servers.append({
                    "name": name,
                    "url": config["url"],
                    "headers": config.get("headers") or {},
                })

        # 2. Name references → look up in instance-level mcp_servers table
        resolved_names = {s["name"] for s in mcp_servers}
        for mcp_name in (agent_def.get("mcp_servers") or []):
            if mcp_name in resolved_names:
                continue
            mcp = await db.get_mcp_server(mcp_name)
            if mcp:
                mcp_servers.append({
                    "name": mcp["name"],
                    "url": mcp["url"],
                    "headers": mcp.get("headers") or {},
                })

    # Load sub-agents for orchestrator agents (injected into prompt context)
    sub_agents = []
    if agent_def:
        subs = await db.list_sub_agents(
            agent_def["name"],
            user_id=job_user_id,
        )
        sub_agents = [
            {"name": s["name"], "description": s.get("description", "")}
            for s in subs
        ]

    return {
        "job": job,
        "agent": {
            "name": agent_def["name"],
            "description": agent_def["description"],
            "prompt_template": agent_def["prompt_template"],
            "tools": list(agent_def.get("tools") or []),
            "knowledge_areas": list(
                agent_def.get("knowledge_areas") or []
            ),
            "max_iterations": agent_def.get("max_iterations"),
            "parent_agent": agent_def.get("parent_agent"),
        } if agent_def else None,
        "sub_agents": sub_agents,
        "messages": messages,
        "knowledge": knowledge,
        "mcp_servers": mcp_servers,
    }


class JobResult(BaseModel):
    output: str
    tokens_used: int = 0


@router.post("/{job_id}/result")
async def report_result(
    job_id: str,
    result: JobResult,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker reports job completion."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    await db.complete_job(job_id, result.output, result.tokens_used)

    # If there's a conversation, save the response and notify gateways
    job = await db.get_job(job_id)
    if job and job["conversation_id"]:
        await db.insert_message(
            conversation_id=job["conversation_id"],
            role="assistant",
            content=result.output,
            agent_name=job["agent_name"],
        )

        conv = await db.get_conversation(job["conversation_id"])
        if conv:
            bus = request.app.state.bus
            await bus.publish(
                Event(
                    type=MESSAGE_RESPONSE,
                    data={
                        "gateway": conv["gateway"],
                        "gateway_thread_id": conv["gateway_thread_id"],
                        "conversation_id": job["conversation_id"],
                        "text": result.output,
                        "agent_name": job["agent_name"],
                    },
                )
            )

    return {"status": "ok"}


class JobError(BaseModel):
    error: str


@router.post("/{job_id}/error")
async def report_error(
    job_id: str,
    err: JobError,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker reports job failure."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    await db.fail_job(job_id, err.error)
    return {"status": "ok"}


@router.post("/{job_id}/heartbeat")
async def job_heartbeat(
    job_id: str,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker reports job is still running."""
    _check_worker_key(request, x_worker_key)
    return {"status": "ok"}
