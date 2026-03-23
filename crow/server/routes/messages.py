from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class InboundMessage(BaseModel):
    text: str
    thread_id: str = "default"
    agent: str | None = None


@router.post("/messages")
async def inbound_message(msg: InboundMessage, request: Request):
    """Receive a message via the API gateway."""
    api_gateway = request.app.state.api_gateway
    await api_gateway.handle_inbound(
        gateway_thread_id=msg.thread_id,
        text=msg.text,
        agent=msg.agent,
    )
    return {"status": "accepted", "thread_id": msg.thread_id}
