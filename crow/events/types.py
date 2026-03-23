from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: uuid4().hex)


# Event type constants
MESSAGE_INBOUND = "message.inbound"
MESSAGE_ROUTED = "message.routed"
MESSAGE_RESPONSE = "message.response"
JOB_CREATED = "job.created"
JOB_STARTED = "job.started"
JOB_COMPLETED = "job.completed"
JOB_FAILED = "job.failed"
KNOWLEDGE_UPDATED = "knowledge.updated"
STATE_UPDATED = "state.updated"
