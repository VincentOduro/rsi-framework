"""
Protocol — structured formats for orchestrator-worker communication.

The orchestrator (Claude) and worker (MiniMax) never talk directly.
They exchange structured messages through the bus. These dataclasses
define the contract.

Design principle: the worker proposes, the bus validates, the orchestrator reviews.
Nobody touches files except the bus, and the bus enforces RSI rules.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import json
import re


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


class ChangeAction(str, Enum):
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"


@dataclass
class FileChange:
    """A single proposed file modification from the worker."""
    path: str
    action: ChangeAction
    content: str = ""         # Full content for create, new content for edit
    original: str = ""        # Original content (for edit — enables diff)
    explanation: str = ""     # Why this change

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "action": self.action.value,
            "content": self.content,
            "original": self.original,
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FileChange":
        return cls(
            path=d["path"],
            action=ChangeAction(d.get("action", "edit")),
            content=d.get("content", ""),
            original=d.get("original", ""),
            explanation=d.get("explanation", ""),
        )


@dataclass
class Task:
    """A structured task from orchestrator to worker."""
    id: str
    type: TaskType
    description: str
    files_to_read: list[str] = field(default_factory=list)
    file_contents: dict[str, str] = field(default_factory=dict)  # pre-loaded by bus
    acceptance_criteria: list[str] = field(default_factory=list)
    context: str = ""                 # FAIL-index entries, patterns, etc.
    fail_entries: list[str] = field(default_factory=list)
    max_retries: int = 3
    attempt: int = 1
    prior_feedback: str = ""          # From orchestrator on revision

    def to_prompt(self) -> str:
        """Convert to a prompt string for the worker model."""
        lines = [
            f"## Task: {self.description}",
            f"Type: {self.type.value}",
            f"Attempt: {self.attempt}/{self.max_retries}",
            "",
        ]

        if self.acceptance_criteria:
            lines.append("## Acceptance Criteria")
            for i, c in enumerate(self.acceptance_criteria, 1):
                lines.append(f"{i}. {c}")
            lines.append("")

        if self.file_contents:
            lines.append("## File Contents")
            for path, content in self.file_contents.items():
                lines.append(f"### {path}")
                lines.append(f"```\n{content}\n```")
                lines.append("")

        if self.fail_entries:
            lines.append("## Known Failure Modes (FAIL-index)")
            for entry in self.fail_entries:
                lines.append(f"- {entry}")
            lines.append("")

        if self.context:
            lines.append("## Additional Context")
            lines.append(self.context)
            lines.append("")

        if self.prior_feedback:
            lines.append("## Feedback From Prior Attempt")
            lines.append(self.prior_feedback)
            lines.append("")

        lines.append("## Required Output Format")
        lines.append("Respond with valid JSON matching this schema:")
        lines.append("```json")
        lines.append(json.dumps({
            "status": "complete|partial|failed",
            "changes": [{"path": "file.py", "action": "create|edit|delete", "content": "...", "explanation": "..."}],
            "explanation": "What was done and why",
            "proof_wrong": "MANDATORY: one specific, testable thing that could prove this change wrong",
            "confidence": 0.85,
        }, indent=2))
        lines.append("```")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class TaskResult:
    """Structured result from worker back to orchestrator."""
    task_id: str
    status: str               # "complete", "partial", "failed"
    changes: list[FileChange] = field(default_factory=list)
    explanation: str = ""
    proof_wrong: str = ""     # Mandatory
    confidence: float = 0.0   # 0.0 to 1.0
    error: str = ""           # If status == "failed"
    raw_response: str = ""    # Full model output for debugging

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "changes": [c.to_dict() for c in self.changes],
            "explanation": self.explanation,
            "proof_wrong": self.proof_wrong,
            "confidence": self.confidence,
            "error": self.error,
        }

    @classmethod
    def from_worker_json(cls, task_id: str, raw: str) -> "TaskResult":
        """Parse worker model's JSON response into a TaskResult.

        Handles messy LLM output: extracts JSON from markdown code blocks,
        handles missing fields gracefully.
        """
        # Extract JSON from markdown code blocks if present
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        json_str = json_match.group(1) if json_match else raw

        try:
            data = json.loads(json_str.strip())
        except json.JSONDecodeError:
            return cls(
                task_id=task_id,
                status="failed",
                error=f"Worker returned invalid JSON",
                raw_response=raw[:2000],
            )

        changes = []
        for c in data.get("changes", []):
            try:
                changes.append(FileChange.from_dict(c))
            except (KeyError, ValueError):
                pass

        return cls(
            task_id=task_id,
            status=data.get("status", "complete"),
            changes=changes,
            explanation=data.get("explanation", ""),
            proof_wrong=data.get("proof_wrong", ""),
            confidence=float(data.get("confidence", 0.5)),
            raw_response=raw[:2000],
        )


@dataclass
class ReviewDecision:
    """Orchestrator's decision on a worker result."""
    task_id: str
    decision: Decision
    feedback: str = ""
    issues: list[str] = field(default_factory=list)
    proof_wrong_quality: int = 0  # 0-100 score

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "decision": self.decision.value,
            "feedback": self.feedback,
            "issues": self.issues,
            "proof_wrong_quality": self.proof_wrong_quality,
        }

    @classmethod
    def from_orchestrator_json(cls, task_id: str, raw: str) -> "ReviewDecision":
        """Parse orchestrator's JSON review into a ReviewDecision."""
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        json_str = json_match.group(1) if json_match else raw

        try:
            data = json.loads(json_str.strip())
        except json.JSONDecodeError:
            # If orchestrator didn't return JSON, treat as accept with feedback
            return cls(
                task_id=task_id,
                decision=Decision.ACCEPT,
                feedback=raw[:500],
            )

        decision_str = data.get("decision", "accept").lower()
        try:
            decision = Decision(decision_str)
        except ValueError:
            decision = Decision.ACCEPT

        return cls(
            task_id=task_id,
            decision=decision,
            feedback=data.get("feedback", ""),
            issues=data.get("issues", []),
            proof_wrong_quality=int(data.get("proof_wrong_quality", 50)),
        )


def generate_task_id() -> str:
    """Generate a unique task ID."""
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    import random
    return f"T-{ts}-{random.randint(100, 999)}"
