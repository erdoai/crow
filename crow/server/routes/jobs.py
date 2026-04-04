"""Job queue endpoints — public listing + worker-facing claim/result."""

import json as _json
import logging
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from crow.auth.dependencies import get_current_user
from crow.auth.session import create_job_token
from crow.events.types import (
    JOB_COMPLETED,
    JOB_CREATED,
    JOB_FAILED,
    JOB_PROGRESS,
    JOB_STARTED,
    MESSAGE_CHUNK,
    MESSAGE_RESPONSE,
    STATE_UPDATED,
    Event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs")


async def _send_push_notification(db, user_id: str, title: str, body: str) -> None:
    """Best-effort push notification — never raises."""
    try:
        from crow.notifications.apns import notify_user
        await notify_user(db, user_id, title, body)
    except Exception:
        logger.debug("Push notification skipped (not configured or failed)")


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
    source: str | None = None,
    limit: int = 50,
    max_age_hours: int | None = 48,
):
    """List recent jobs. Defaults to last 48 hours; pass max_age_hours=0 for all."""
    user = await get_current_user(request)
    uid = _user_id_from_request(request, user)
    db = request.app.state.db
    age = max_age_hours if max_age_hours else None
    return await db.list_jobs(
        status=status, source=source, limit=limit,
        user_id=uid, max_age_hours=age,
    )


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


class CreateJobPayload(BaseModel):
    agent_name: str
    input: str
    conversation_id: str | None = None
    mode: str = "background"
    user_id: str | None = None


@router.post("")
async def create_job_direct(
    payload: CreateJobPayload,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker-facing: create a job directly (e.g. spawn_job tool).

    Background jobs get their own conversation so their intermediate turns
    don't pollute the parent chat.  The parent conversation is stored in
    parent_conversation_id — post_update and final results go there.
    """
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    bus = request.app.state.bus

    parent_conversation_id = None
    job_conversation_id = payload.conversation_id

    if payload.mode == "background" and payload.conversation_id:
        # Create a dedicated conversation for this background job.
        # Each spawn gets a unique conversation (uuid in thread_id).
        parent_conversation_id = payload.conversation_id
        parent_conv = await db.get_conversation(parent_conversation_id)
        user_id = parent_conv.get("user_id") if parent_conv else payload.user_id
        bg_conv = await db.get_or_create_conversation(
            gateway="background",
            gateway_thread_id=f"bg-{uuid4().hex}",
            user_id=user_id,
        )
        job_conversation_id = bg_conv["id"]
        # Title the bg conversation so it's identifiable in the sidebar
        title = f"{payload.agent_name}: {payload.input[:50]}"
        if len(payload.input) > 50:
            title = title.rsplit(" ", 1)[0] + "..."
        await db.set_conversation_title(bg_conv["id"], title)

    job_id = await db.create_job(
        agent_name=payload.agent_name,
        input_text=payload.input,
        conversation_id=job_conversation_id,
        mode=payload.mode,
        parent_conversation_id=parent_conversation_id,
    )

    await bus.publish(Event(
        type=JOB_CREATED,
        data={
            "job_id": job_id,
            "agent_name": payload.agent_name,
            "conversation_id": job_conversation_id,
            "text": payload.input,
            "mode": payload.mode,
        },
    ))

    return {"status": "created", "job_id": job_id}


# -- Worker-facing --


async def _build_personal_agent_payload(
    db, job: dict, user_id: str, job_token: str, messages: list[dict],
) -> dict:
    """Compose the personal agent payload from user_agent + skills."""
    from crow.worker.prompt import render_prompt

    user_agent = await db.get_or_create_user_agent(user_id)
    user = await db.get_user(user_id)
    display_name = user["display_name"] if user else "there"
    skills = await db.list_skills_for_user(user_id)

    # Load pinned knowledge (soul, identity docs) — always in system prompt
    pinned = await db.get_pinned_knowledge(user_id)
    soul_entries = [e for e in pinned if e["category"] == "soul"]

    # Render system prompt from template
    prompt = render_prompt("personal_agent.md.j2", {
        "agent_name": user_agent["agent_name"],
        "soul_entries": soul_entries,
        "user_display_name": display_name,
        "skills": skills,
    })

    # Union all tools from all skills + core personal agent tools
    all_tools = set()
    for s in skills:
        for t in (s.get("tools") or []):
            all_tools.add(t)
    # Always give the personal agent these core tools
    all_tools.update([
        "knowledge_search", "knowledge_write",
        "store_get", "store_set", "store_append", "store_list",
        "progress_update", "spawn_job", "schedule",
        "set_agent_name", "set_user_name",
    ])

    # Union all MCP servers from all skills
    mcp_servers = []
    resolved_names: set[str] = set()
    for s in skills:
        # Inline MCP configs
        mcp_configs = s.get("mcp_configs")
        if mcp_configs:
            if isinstance(mcp_configs, str):
                mcp_configs = _json.loads(mcp_configs)
            for name, config in mcp_configs.items():
                if name not in resolved_names:
                    mcp_servers.append({
                        "name": name,
                        "url": config["url"],
                        "headers": config.get("headers") or {},
                    })
                    resolved_names.add(name)
        # Name references
        for mcp_name in (s.get("mcp_servers") or []):
            if mcp_name not in resolved_names:
                mcp = await db.get_mcp_server(mcp_name)
                if mcp:
                    mcp_servers.append({
                        "name": mcp["name"],
                        "url": mcp["url"],
                        "headers": mcp.get("headers") or {},
                    })
                    resolved_names.add(mcp_name)

    # Load all knowledge for this user (not agent-scoped)
    knowledge = await db.search_knowledge(user_id=user_id, limit=20)

    return {
        "job": {**job, "user_id": user_id},
        "job_token": job_token,
        "agent": {
            "name": user_agent["agent_name"],
            "description": f"{display_name}'s personal agent",
            "prompt_template": prompt,
            "tools": sorted(all_tools),
            "knowledge_areas": [],
            "max_iterations": 25,
        },
        "sub_agents": [],
        "messages": messages,
        "knowledge": knowledge,
        "mcp_servers": mcp_servers,
    }


@router.get("/next/claim")
async def claim_next_job(request: Request, x_worker_key: str = Header()):
    """Worker claims the next pending job."""
    _check_worker_key(request, x_worker_key)
    worker_id = request.headers.get("x-worker-id", "unknown")

    db = request.app.state.db
    job = await db.claim_next_job(worker_id)
    if not job:
        return None

    bus = request.app.state.bus
    await bus.publish(Event(
        type=JOB_STARTED,
        data={
            "job_id": job["id"],
            "agent_name": job["agent_name"],
            "conversation_id": job.get("conversation_id"),
            "parent_conversation_id": job.get("parent_conversation_id"),
            "input": job.get("input", ""),
            "source": job.get("source", "message"),
            "mode": job.get("mode", "chat"),
        },
    ))

    # Resolve user_id from the job's conversation
    job_user_id = None
    if job.get("conversation_id"):
        conv = await db.get_conversation(job["conversation_id"])
        if conv:
            job_user_id = conv.get("user_id")

    # Load conversation history with attachments
    messages = []
    if job["conversation_id"]:
        messages = await db.get_messages(job["conversation_id"])
        if messages:
            msg_ids = [m["id"] for m in messages]
            attachments_by_msg = await db.get_attachments_for_messages(msg_ids)
            for msg in messages:
                msg["attachments"] = attachments_by_msg.get(msg["id"], [])

    # Issue a short-lived job token encoding user_id — workers use this
    # for user-scoped API calls (knowledge, state) during execution.
    secret = request.app.state.auth_config.get("session_secret", "")
    job_token = create_job_token(job["id"], job_user_id, secret)

    # --- Personal agent path ---
    if job["agent_name"] == "personal" and job_user_id:
        return await _build_personal_agent_payload(
            db, job, job_user_id, job_token, messages,
        )

    # --- Classic agent_def path (backward compat) ---
    agent_def = await db.get_agent_def(job["agent_name"], user_id=job_user_id)

    knowledge = []
    if agent_def and agent_def.get("knowledge_areas"):
        knowledge = await db.search_knowledge(
            agent_name=job["agent_name"],
            user_id=job_user_id,
            limit=20,
        )

    # Load MCP server configs — agent-level inline configs override instance-level
    mcp_servers = []
    if agent_def:
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

    sub_agents = []
    if agent_def:
        subs = await db.list_sub_agents(
            agent_def["name"],
            user_id=job_user_id,
        )
        if subs:
            sub_agents = [
                {"name": s["name"], "description": s.get("description", "")}
                for s in subs
            ]
        elif "delegate_to_agent" in (agent_def.get("tools") or []):
            all_agents = await db.list_agent_defs(user_id=job_user_id)
            sub_agents = [
                {"name": a["name"], "description": a.get("description", "")}
                for a in all_agents
                if a["name"] != agent_def["name"]
            ]

    return {
        "job": {**job, "user_id": job_user_id},
        "job_token": job_token,
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


class ChunkPayload(BaseModel):
    type: str = "text"  # "text" or "tool_call"
    text: str | None = None
    tool_name: str | None = None
    agent_name: str | None = None


@router.post("/{job_id}/chunk")
async def job_chunk(
    job_id: str,
    payload: ChunkPayload,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker streams a text chunk during agent execution."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    bus = request.app.state.bus

    # Resolve conversation_id from job
    job = await db.get_job(job_id)
    if not job or not job.get("conversation_id"):
        return {"status": "ok"}

    await bus.publish(Event(
        type=MESSAGE_CHUNK,
        data={
            "conversation_id": job["conversation_id"],
            "job_id": job_id,
            "type": payload.type,
            "text": payload.text,
            "tool_name": payload.tool_name,
            "agent_name": payload.agent_name,
            "mode": job.get("mode", "chat"),
        },
    ))
    return {"status": "ok"}


class ProgressPayload(BaseModel):
    status: str
    data: dict | None = None
    agent_name: str | None = None


@router.post("/{job_id}/progress")
async def job_progress(
    job_id: str,
    payload: ProgressPayload,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker reports mid-run progress — written to state channel for dashboards."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    bus = request.app.state.bus

    # Resolve user_id from job's conversation
    user_id = None
    job = await db.get_job(job_id)
    if job and job.get("conversation_id"):
        conv = await db.get_conversation(job["conversation_id"])
        if conv:
            user_id = conv.get("user_id")

    state_key = f"progress:{job_id}"
    state_data = {
        "agent_name": payload.agent_name or (job["agent_name"] if job else "unknown"),
        "job_id": job_id,
        "status": payload.status,
        **(payload.data or {}),
    }
    await db.set_state(state_key, state_data, user_id=user_id)
    await bus.publish(Event(
        type=STATE_UPDATED,
        data={"key": state_key, "data": state_data, "user_id": user_id},
    ))
    await bus.publish(Event(
        type=JOB_PROGRESS,
        data={
            "job_id": job_id,
            "conversation_id": job.get("conversation_id") if job else None,
            "agent_name": payload.agent_name or (job["agent_name"] if job else "unknown"),
            "status": payload.status,
            "data": payload.data,
        },
    ))
    return {"status": "ok"}


class TurnPayload(BaseModel):
    role: str
    content: list | str  # Structured content blocks or plain text


@router.post("/{job_id}/turn")
async def save_turn(
    job_id: str,
    payload: TurnPayload,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker saves an intermediate conversation turn during execution."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    job = await db.get_job(job_id)
    if not job or not job.get("conversation_id"):
        return {"status": "ok"}
    await db.insert_message(
        conversation_id=job["conversation_id"],
        role=payload.role,
        content=payload.content,
        agent_name=job["agent_name"] if payload.role == "assistant" else None,
    )
    return {"status": "ok"}


@router.post("/{job_id}/requeue")
async def requeue_job(
    job_id: str,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker requeues a job for another worker (graceful shutdown)."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    await db.requeue_job(job_id)
    return {"status": "ok"}


class JobResult(BaseModel):
    output: list | str
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
    bus = request.app.state.bus
    await db.complete_job(job_id, result.output, result.tokens_used)

    # If there's a conversation, save the response and notify gateways
    job = await db.get_job(job_id)

    agent_name = job["agent_name"] if job else "unknown"
    job_mode = job.get("mode", "chat") if job else "chat"

    await bus.publish(Event(
        type=JOB_COMPLETED,
        data={
            "job_id": job_id,
            "agent_name": agent_name,
            "mode": job_mode,
        },
    ))

    if job and job["conversation_id"]:
        is_bg = bool(job.get("parent_conversation_id"))

        if is_bg:
            # Background job done — trigger a chat job on the parent
            # conversation so the main agent can summarise the results
            # for the user (instead of dumping raw internal output).
            parent_conv_id = job["parent_conversation_id"]
            parent_conv = await db.get_conversation(parent_conv_id)

            # Format as a tool result from spawn_job reporting back
            output_text = str(result.output)[:4000] if result.output else "(no output)"
            handoff = (
                f"[spawn_job result: {agent_name} (job_id={job_id}) completed]\n\n"
                f"{output_text}"
            )
            await db.insert_message(
                conversation_id=parent_conv_id,
                role="user",
                content=handoff,
            )

            # Determine which agent should reply on the parent thread
            parent_agent = await db.last_agent_for_conversation(
                parent_conv_id
            ) or agent_name
            followup_job_id = await db.create_job(
                agent_name=parent_agent,
                input_text=handoff,
                conversation_id=parent_conv_id,
            )
            await bus.publish(Event(
                type=JOB_CREATED,
                data={
                    "job_id": followup_job_id,
                    "agent_name": parent_agent,
                    "conversation_id": parent_conv_id,
                    "text": handoff,
                },
            ))

            if parent_conv and parent_conv.get("user_id"):
                await _send_push_notification(
                    db, parent_conv["user_id"],
                    f"{agent_name} completed",
                    str(result.output)[:100],
                )
        else:
            # Chat jobs: turns are already in the conversation via
            # _save_turn. Just notify the frontend the job is done.
            conv = await db.get_conversation(job["conversation_id"])
            if conv:
                await bus.publish(
                    Event(
                        type=MESSAGE_RESPONSE,
                        data={
                            "gateway": conv["gateway"],
                            "gateway_thread_id": conv["gateway_thread_id"],
                            "conversation_id": job["conversation_id"],
                            "text": result.output,
                            "agent_name": agent_name,
                        },
                    )
                )
                if conv.get("user_id"):
                    await _send_push_notification(
                        db, conv["user_id"],
                        f"{agent_name} completed",
                        str(result.output)[:100],
                    )

    return {"status": "ok"}


class AttachmentPayload(BaseModel):
    filename: str
    content_type: str
    data: str  # base64
    size_bytes: int


@router.post("/{job_id}/attachments")
async def create_job_attachment(
    job_id: str,
    payload: AttachmentPayload,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker creates a file attachment during agent execution."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    att_id = await db.insert_attachment_for_job(
        job_id=job_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        data=payload.data,
    )
    return {"id": att_id, "filename": payload.filename}


@router.get("/{job_id}/evaluation-data")
async def get_job_evaluation_data(
    job_id: str,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker fetches job + conversation messages for evaluation."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    messages = []
    if job.get("conversation_id"):
        messages = await db.get_messages(job["conversation_id"])
    return {"job": dict(job), "messages": [dict(m) for m in messages]}


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

    job = await db.get_job(job_id)

    bus = request.app.state.bus
    await bus.publish(Event(
        type=JOB_FAILED,
        data={
            "job_id": job_id,
            "error": err.error,
            "conversation_id": job["conversation_id"] if job else None,
            "agent_name": job["agent_name"] if job else None,
        },
    ))
    if job and job.get("conversation_id"):
        conv = await db.get_conversation(job["conversation_id"])
        if conv and conv.get("user_id"):
            await _send_push_notification(
                db, conv["user_id"],
                f"{job['agent_name']} failed",
                err.error[:100],
            )

    return {"status": "ok"}


@router.post("/{job_id}/heartbeat")
async def job_heartbeat(
    job_id: str,
    request: Request,
    x_worker_key: str = Header(),
):
    """Worker reports job is still running — resets the reaper clock."""
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    await db.job_heartbeat(job_id)
    return {"status": "ok"}


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    """User cancels a running job."""
    db = request.app.state.db
    bus = request.app.state.bus
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] not in ("pending", "running"):
        return {"status": "already_finished"}
    await db.fail_job(job_id, "Cancelled by user")
    await bus.publish(Event(
        type=JOB_FAILED,
        data={"job_id": job_id, "error": "Cancelled by user"},
    ))
    return {"status": "cancelled"}


class UpdateMessage(BaseModel):
    text: str
    agent_name: str | None = None


@router.post("/{job_id}/update-message")
async def post_update_message(
    job_id: str,
    payload: UpdateMessage,
    request: Request,
    x_worker_key: str = Header(),
):
    """Post a message to the conversation thread during a background job.

    If the job has a parent_conversation_id (background job with its own
    conversation), post to the parent so the user sees the update in chat.
    """
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    bus = request.app.state.bus

    job = await db.get_job(job_id)
    if not job or not job.get("conversation_id"):
        return {"status": "ok"}

    # Post to the parent conversation if this is a background job
    target_conv_id = job.get("parent_conversation_id") or job["conversation_id"]

    agent_name = payload.agent_name or job.get("agent_name", "agent")
    msg_id = await db.insert_message(
        conversation_id=target_conv_id,
        role="assistant",
        content=payload.text,
        agent_name=agent_name,
    )

    conv = await db.get_conversation(target_conv_id)
    if conv:
        await bus.publish(Event(
            type=MESSAGE_RESPONSE,
            data={
                "gateway": conv["gateway"],
                "gateway_thread_id": conv["gateway_thread_id"],
                "conversation_id": target_conv_id,
                "text": payload.text,
                "agent_name": agent_name,
                "message_id": msg_id,
            },
        ))

    return {"status": "ok", "message_id": msg_id}
