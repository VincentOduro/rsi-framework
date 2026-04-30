"""Protocol — structured formats for orchestrator-worker communication.

The orchestrator (Claude) and worker (MiniMax) never talk directly.
They exchange structured messages through the bus. These models
define the contract.

Design principle: the worker proposes, the bus validates, the orchestrator reviews.
Nobody touches files except the bus, and the bus enforces RSI rules.
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskType(str, Enum):
    IMPLEMENT = "implement"
    FIX = "fix"
    REFACTOR = "refactor"
    REVIEW = "review"
    TEST = "test"
    DOCS = "docs"


class Decision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    REVISE = "revise"


class Capability(str, Enum):
    TEXT = "text"
    IMAGE = "image"


class ChangeAction(str, Enum):
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"


class TaskSpec(BaseModel):
    """Models .rsi/tasks/TASK-NNN.json (per scripts/delegate.py validate_task)."""

    id: str
    description: str
    instruction: str
    files_to_read: list[str] = Field(default_factory=list)
    files_to_modify: list[str]
    acceptance_criteria: list[str]
    proof_wrong: str
    constraints: list[str] = Field(default_factory=list)
    task_kind: str = "code"
    image_aspect_ratio: str = "1:1"
    image_outputs: list[str] = Field(default_factory=list)
    image_model: str = "image-01"

    model_config = ConfigDict(extra="allow")

    @field_validator("id", "description", "instruction", "proof_wrong")
    @classmethod
    def must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must be non-empty")
        return v

    @field_validator("files_to_modify", "acceptance_criteria")
    @classmethod
    def must_have_items(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("List must have at least one item")
        return v

    @model_validator(mode="after")
    def _check_image_fields(self):
        if self.task_kind == "image":
            if not self.image_outputs:
                raise ValueError("image_outputs must be non-empty when task_kind is 'image'")
            if len(self.files_to_modify) != len(self.image_outputs):
                raise ValueError("files_to_modify and image_outputs must have the same length")
            if set(self.files_to_modify) != set(self.image_outputs):
                raise ValueError("files_to_modify and image_outputs must contain the same items")
        return self


class ImageOutput(BaseModel):
    path: str
    request_id: str = ""
    prompt: str = ""
    model: str = ""
    aspect_ratio: str = ""
    bytes: int = 0
    url: str = ""

    model_config = ConfigDict(extra="allow")


class WorkerResult(BaseModel):
    """Models .memory/reviews/results/TASK-NNN.json (per scripts/delegate.py call_worker)."""

    changes: dict[str, str] = Field(default_factory=dict)
    proof_wrong: str = ""
    notes: str = ""
    raw_response: str = ""
    tokens_used: int = 0
    latency_seconds: float = 0.0
    error: str = ""
    image_outputs: list[ImageOutput] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ReviewDecision(BaseModel):
    """Orchestrator's decision on a worker result."""

    task_id: str
    decision: Decision
    feedback: str = ""
    issues: list[str] = Field(default_factory=list)
    proof_wrong_quality: int = Field(default=0, ge=0, le=100)


class DelegationEvent(BaseModel):
    """Models rows in .memory/metrics/delegations.jsonl (per scripts/review_queue.py)."""

    task_id: str
    verdict: str  # PENDING | ACCEPTED | REJECTED | REVISED
    timestamp: str = ""
    reviewed_at: str = ""

    model_config = ConfigDict(extra="allow")


def generate_task_id() -> str:
    """Generate a unique task ID."""
    ts = datetime.now(UTC).strftime("%H%M%S")
    import random

    return f"T-{ts}-{random.randint(100, 999)}"
