from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from pomo_cli.models import TaskRecord
from pomo_cli.store import PomoStore


@dataclass(frozen=True)
class StatusPayload:
    state: str
    task_id: str
    task_title: str
    planned_minutes: int
    starts_at: datetime
    ends_at: datetime
    remaining_seconds: int
    total_elapsed_seconds: int
    completed_at: datetime | None


@dataclass(frozen=True)
class SummaryPayload:
    tasks_completed: int
    total_time_spent_today: int
    time_spent_by_task: dict[str, int]


class PomoService:
    def __init__(self, store: PomoStore) -> None:
        self.store = store

    def start_new_task(
        self,
        task_title: str,
        planned_minutes: int,
        now: datetime,
    ) -> StatusPayload:
        self._assert_no_running_session()
        task_id = self._next_task_id(now)
        self.store.create_task_with_session(
            task_id=task_id,
            task_title=task_title,
            state="running",
            created_at=now,
            session_id=uuid4().hex,
            planned_minutes=planned_minutes,
            started_at=now,
        )
        return self.get_status(now=now)

    def start_existing_task(
        self,
        task_ref: str | None,
        use_latest: bool,
        planned_minutes: int,
        now: datetime,
    ) -> StatusPayload:
        self._assert_no_running_session()
        task = self._resolve_task(task_ref=task_ref, use_latest=use_latest)
        self._assert_task_not_completed(task, "cannot start a completed task")
        self.store.update_task_state_with_new_session(
            task_id=task.task_id,
            state="running",
            updated_at=now,
            completed_at=None,
            session_id=uuid4().hex,
            planned_minutes=planned_minutes,
            started_at=now,
        )
        return self.get_status(now=now)

    def close_active_session(self, now: datetime) -> StatusPayload:
        session = self.store.get_active_session()
        if session is None:
            raise RuntimeError("no active session")

        elapsed_seconds = max(0, int((now - session.started_at).total_seconds()))
        self.store.finalize_session(
            task_id=session.task_id,
            session_id=session.session_id,
            ended_at=now,
            elapsed_seconds=elapsed_seconds,
            state="session_closed",
            updated_at=now,
            completed_at=None,
        )
        return self.get_task_status(session.task_id, now=now)

    def complete_task(
        self,
        task_ref: str | None,
        use_latest: bool,
        now: datetime,
    ) -> StatusPayload:
        task = self._resolve_task(task_ref=task_ref, use_latest=use_latest)
        self._assert_task_not_completed(task, "task is already completed")
        active_session = self.store.get_active_session()
        if active_session is not None and active_session.task_id == task.task_id:
            elapsed_seconds = max(0, int((now - active_session.started_at).total_seconds()))
            self.store.finalize_session(
                task_id=task.task_id,
                session_id=active_session.session_id,
                ended_at=now,
                elapsed_seconds=elapsed_seconds,
                state="completed",
                updated_at=now,
                completed_at=now,
            )
        else:
            self.store.update_task_state(
                task_id=task.task_id,
                state="completed",
                updated_at=now,
                completed_at=now,
            )
        return self.get_task_status(task.task_id, now=now)

    def get_status(self, now: datetime | None = None) -> StatusPayload:
        active_session = self.store.get_active_session()
        if active_session is not None:
            return self.get_task_status(active_session.task_id, now=now)

        latest_task = self.store.get_latest_task()
        if latest_task is None:
            raise RuntimeError("no tracked task")
        return self.get_task_status(latest_task.task_id, now=now)

    def get_task_status(
        self,
        task_id: str,
        now: datetime | None = None,
    ) -> StatusPayload:
        task = self.store.get_task(task_id)
        session = self.store.get_latest_session_for_task(task_id)
        if session is None:
            raise RuntimeError(f"task {task_id} has no session history")

        ends_at = session.started_at + timedelta(minutes=session.planned_minutes)
        remaining_seconds = 0
        if task.state == "running":
            current_time = now or datetime.now()
            remaining_seconds = max(0, int((ends_at - current_time).total_seconds()))

        return StatusPayload(
            state=task.state,
            task_id=task.task_id,
            task_title=task.task_title,
            planned_minutes=session.planned_minutes,
            starts_at=session.started_at,
            ends_at=ends_at,
            remaining_seconds=remaining_seconds,
            total_elapsed_seconds=task.total_elapsed_seconds,
            completed_at=task.completed_at,
        )

    def summary_for_date(self, day: str) -> SummaryPayload:
        completed_tasks = self.store.get_completed_tasks_for_date(day)
        time_spent_by_task: dict[str, int] = {}
        for task in completed_tasks:
            time_spent_by_task[task.task_title] = (
                time_spent_by_task.get(task.task_title, 0)
                + task.total_elapsed_seconds
            )
        return SummaryPayload(
            tasks_completed=len(completed_tasks),
            total_time_spent_today=sum(
                task.total_elapsed_seconds for task in completed_tasks
            ),
            time_spent_by_task=time_spent_by_task,
        )

    def _assert_no_running_session(self) -> None:
        if self.store.get_active_session() is not None:
            raise RuntimeError("an active session is already running")

    def _resolve_task(self, task_ref: str | None, use_latest: bool) -> TaskRecord:
        if use_latest:
            latest_task = self.store.get_latest_task()
            if latest_task is None:
                raise RuntimeError("no tracked task")
            return latest_task

        if task_ref is None:
            raise RuntimeError("task reference is required")
        return self.store.get_task(task_ref)

    @staticmethod
    def _assert_task_not_completed(task: TaskRecord, message: str) -> None:
        if task.state == "completed":
            raise RuntimeError(message)

    def _next_task_id(self, now: datetime) -> str:
        task_count = self.store.count_tasks_created_on_date(now.date().isoformat())
        return f"{now.strftime('%Y-%d%m')}-{task_count + 1:04d}"
