from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    task_title: str
    state: str
    total_elapsed_seconds: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    estimate_minutes: int | None = None
    priority: str | None = None
    source_parent_title: str | None = None
    position: int | None = None


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    task_id: str
    planned_minutes: int
    started_at: datetime
    ended_at: datetime | None
    elapsed_seconds: int


@dataclass(frozen=True)
class SummaryTaskEntry:
    task_id: str
    task_title: str
    elapsed_seconds: int


@dataclass(frozen=True)
class BacklogEntry:
    position: int
    task_id: str
    task_title: str
    estimate_minutes: int
    priority: str
    source_parent_title: str | None
    state: str
