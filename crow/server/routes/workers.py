from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/workers")


def _check_worker_key(request: Request, x_worker_key: str = Header()) -> None:
    expected = request.app.state.settings.worker_api_key
    if x_worker_key != expected:
        raise HTTPException(status_code=401, detail="Invalid worker key")


class RegisterRequest(BaseModel):
    worker_id: str
    name: str | None = None


@router.post("/register")
async def register_worker(req: RegisterRequest, request: Request, x_worker_key: str = Header()):
    _check_worker_key(request, x_worker_key)
    db = request.app.state.db
    await db.register_worker(req.worker_id, req.name)
    return {"status": "registered", "worker_id": req.worker_id}


@router.post("/heartbeat")
async def heartbeat(request: Request, x_worker_key: str = Header()):
    _check_worker_key(request, x_worker_key)
    worker_id = request.headers.get("x-worker-id", "unknown")
    db = request.app.state.db
    await db.worker_heartbeat(worker_id)
    return {"status": "ok"}


@router.get("")
async def list_workers(request: Request):
    db = request.app.state.db
    return await db.list_workers()
