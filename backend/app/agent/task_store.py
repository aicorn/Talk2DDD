"""In-memory task store for async agent chat tasks."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Tasks that have completed or failed are kept in memory for this many seconds
# before being pruned.  Ten minutes gives the frontend plenty of time to
# collect the result even under slow or intermittent network conditions.
TASK_TTL_SECONDS = 600


@dataclass
class TaskRecord:
    task_id: str
    status: str  # "pending" | "completed" | "failed"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskStore:
    """In-memory store for async chat task results.

    All mutations happen on the single asyncio event-loop thread, so no
    additional locking is required.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskRecord] = {}

    def create(self) -> str:
        """Register a new pending task and return its ID."""
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = TaskRecord(task_id=task_id, status="pending")
        return task_id

    def set_result(self, task_id: str, result: Dict[str, Any]) -> None:
        """Mark a task as completed and store its result payload."""
        if task_id in self._tasks:
            rec = self._tasks[task_id]
            rec.status = "completed"
            rec.result = result
            rec.completed_at = datetime.now(timezone.utc)

    def set_error(self, task_id: str, error: str) -> None:
        """Mark a task as failed and store the error message."""
        if task_id in self._tasks:
            rec = self._tasks[task_id]
            rec.status = "failed"
            rec.error = error
            rec.completed_at = datetime.now(timezone.utc)

    def get(self, task_id: str) -> Optional[TaskRecord]:
        """Return the TaskRecord for *task_id*, or ``None`` if unknown."""
        return self._tasks.get(task_id)

    def cleanup_expired(self) -> None:
        """Remove tasks that finished more than ``TASK_TTL_SECONDS`` ago."""
        now = datetime.now(timezone.utc)
        expired = [
            tid
            for tid, rec in self._tasks.items()
            if rec.completed_at
            and (now - rec.completed_at).total_seconds() > TASK_TTL_SECONDS
        ]
        for tid in expired:
            del self._tasks[tid]


# Module-level singleton shared across the entire application process.
_task_store = TaskStore()


def get_task_store() -> TaskStore:
    return _task_store
