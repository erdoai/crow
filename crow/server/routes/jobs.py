"""Worker-facing job queue endpoints."""

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/jobs")


def _check_worker_key(request: Request, x_worker_key: str = Header()) -> None:
    expected = request.app.state.settings.worker_api_key
    if x_worker_key != expected:
        raise HTTPException(status_code=401, detail="Invalid worker key")


@router.get("/next")
async def claim_next_job(request: Request, x_worker_key: str = Header()):
    """Worker claims the next pending job."""
    _check_worker_key(request, x_worker_key)
    worker_id = request.headers.get("x-worker-id", "unknown")

    db = request.app.state.db
    job = await db.claim_next_job(worker_id)
    if not job:
        return None

    # Enrich with agent definition and context
    registry = request.app.state.registry
    agent_def = registry.get(job["agent_name"])

    # Load conversation history if there's a conversation
    messages = []
    if job["conversation_id"]:
        messages = await db.get_messages(job["conversation_id"])

    # Load relevant knowledge
    knowledge = []
    if agent_def and agent_def.knowledge_areas:
        knowledge = await db.search_knowledge(
            agent_name=job["agent_name"],
            limit=20,
        )

    return {
        "job": job,
        "agent": {
            "name": agent_def.name,
            "description": agent_def.description,
            "prompt_template": agent_def.prompt_template,
            "tools": [t.name for t in agent_def.tools],
            "knowledge_areas": agent_def.knowledge_areas,
        } if agent_def else None,
        "messages": messages,
        "knowledge": knowledge,
    }


class JobResult(BaseModel):
    output: str
    tokens_used: int = 0


@router.post("/{job_id}/result")
async def report_result(
    job_id: str, result: JobResult, request: Request, x_worker_key: str = Header()
):
    """Worker reports job completion."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    await db.complete_job(job_id, result.output, result.tokens_used)

    # If there's a conversation, save the response as an assistant message
    job = await db.get_job(job_id)
    if job and job["conversation_id"]:
        await db.insert_message(
            conversation_id=job["conversation_id"],
            role="assistant",
            content=result.output,
            agent_name=job["agent_name"],
        )

        # Publish response event for gateways
        bus = request.app.state.bus
        from crow.events.types import MESSAGE_RESPONSE, Event

        conv = await db.list_conversations()
        matching = [c for c in conv if c["id"] == job["conversation_id"]]
        if matching:
            await bus.publish(
                Event(
                    type=MESSAGE_RESPONSE,
                    data={
                        "gateway": matching[0]["gateway"],
                        "gateway_thread_id": matching[0]["gateway_thread_id"],
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
    job_id: str, err: JobError, request: Request, x_worker_key: str = Header()
):
    """Worker reports job failure."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    await db.fail_job(job_id, err.error)
    return {"status": "ok"}


@router.post("/{job_id}/heartbeat")
async def job_heartbeat(
    job_id: str, request: Request, x_worker_key: str = Header()
):
    """Worker reports job is still running."""
    _check_worker_key(request, x_worker_key)
    # For now just acknowledge — could update a last_heartbeat column
    return {"status": "ok"}
