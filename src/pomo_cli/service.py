from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from pomo_cli.models import BacklogEntry, SummaryTaskEntry, TaskRecord
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
    tasks_worked_on_today: int
    tasks_completed_today: int
    total_time_spent_today: int
    task_entries: list[SummaryTaskEntry]


@dataclass(frozen=True)
class SessionlessStatusPayload:
    state: str
    task_id: str
    task_title: str
    estimate_minutes: int | None
    priority: str | None
    source_parent_title: str | None
    total_elapsed_seconds: int
    completed_at: datetime | None


class PomoService:
    ALLOWED_PRIORITIES = ("high", "medium", "low")

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

    def continue_task(
        self,
        task_ref: str | None,
        planned_minutes: int,
        now: datetime,
    ) -> StatusPayload:
        self._assert_no_running_session()
        task = self._resolve_task(task_ref=task_ref, use_latest=task_ref is None)
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

    def run_planned_task(
        self,
        task_ref: str | None,
        position: int | None,
        planned_minutes: int | None,
        now: datetime,
    ) -> StatusPayload:
        self._assert_no_running_session()
        task = self._resolve_planned_task(
            task_ref=task_ref,
            position=position,
            day=now.date().isoformat(),
        )
        session_minutes = planned_minutes if planned_minutes is not None else task.estimate_minutes
        if session_minutes is None or session_minutes <= 0:
            raise RuntimeError("planned backlog task is missing a valid estimate")

        self.store.update_task_state_with_new_session(
            task_id=task.task_id,
            state="running",
            updated_at=now,
            completed_at=None,
            session_id=uuid4().hex,
            planned_minutes=session_minutes,
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
    ) -> StatusPayload | SessionlessStatusPayload:
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
            return self.get_task_status(task.task_id, now=now)

        if task.state == "planned":
            self.store.update_task_state(
                task_id=task.task_id,
                state="completed",
                updated_at=now,
                completed_at=now,
            )
            return self.get_sessionless_task_status(task.task_id)

        self.store.update_task_state(
            task_id=task.task_id,
            state="completed",
            updated_at=now,
            completed_at=now,
        )
        return self.get_task_status(task.task_id, now=now)

    def get_status(self, now: datetime | None = None) -> StatusPayload | SessionlessStatusPayload:
        active_session = self.store.get_active_session()
        if active_session is not None:
            return self.get_task_status(active_session.task_id, now=now)

        latest_worked = self.store.get_latest_worked_task()
        if latest_worked is not None:
            return self.get_task_status(latest_worked.task_id, now=now)

        latest_planned = self.store.get_latest_planned_task()
        if latest_planned is not None:
            return self.get_sessionless_task_status(latest_planned.task_id)

        raise RuntimeError("no tracked task")

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

    def get_sessionless_task_status(self, task_id: str) -> SessionlessStatusPayload:
        task = self.store.get_task(task_id)
        return SessionlessStatusPayload(
            state=task.state,
            task_id=task.task_id,
            task_title=task.task_title,
            estimate_minutes=task.estimate_minutes,
            priority=task.priority,
            source_parent_title=task.source_parent_title,
            total_elapsed_seconds=task.total_elapsed_seconds,
            completed_at=task.completed_at,
        )

    def summary_for_date(self, day: str) -> SummaryPayload:
        task_entries = self.store.list_task_time_entries_for_date(day)
        return SummaryPayload(
            tasks_worked_on_today=len(task_entries),
            tasks_completed_today=self.store.count_completed_tasks_for_date(day),
            total_time_spent_today=sum(
                entry.elapsed_seconds for entry in task_entries
            ),
            task_entries=task_entries,
        )

    def plan_tasks(
        self,
        parent_title: str,
        subtasks: list[dict[str, object]],
        now: datetime,
    ) -> list[TaskRecord]:
        day = now.date().isoformat()
        created_count = self.store.count_tasks_created_on_date(day)
        backlog_count = self.store.count_backlog_entries_for_date(day)
        validated_subtasks: list[dict[str, object]] = []

        for offset, subtask in enumerate(subtasks, start=1):
            task_title = str(subtask["task_title"]).strip()
            try:
                estimate_minutes = int(subtask["estimate_minutes"])
            except (TypeError, ValueError) as error:
                raise ValueError("estimate_minutes must be a positive integer") from error
            priority = str(subtask["priority"]).strip().lower()

            if not task_title:
                raise ValueError("task title is required")
            if estimate_minutes <= 0:
                raise ValueError("estimate_minutes must be a positive integer")
            if priority not in self.ALLOWED_PRIORITIES:
                allowed = ", ".join(self.ALLOWED_PRIORITIES)
                raise ValueError(f"priority must be one of: {allowed}")

            validated_subtasks.append(
                {
                    "task_id": f"{now.strftime('%Y-%m%d')}-{created_count + offset:04d}",
                    "task_title": task_title,
                    "created_at": now,
                    "estimate_minutes": estimate_minutes,
                    "priority": priority,
                    "source_parent_title": parent_title,
                    "position": backlog_count + offset,
                }
            )

        self.store.create_planned_tasks(validated_subtasks)
        return [self.store.get_task(task["task_id"]) for task in validated_subtasks]

    def backlog_for_date(self, day: str) -> list[BacklogEntry]:
        return self.store.list_backlog_entries_for_date(day)

    def _assert_no_running_session(self) -> None:
        if self.store.get_active_session() is not None:
            raise RuntimeError("an active session is already running")

    def _resolve_task(self, task_ref: str | None, use_latest: bool) -> TaskRecord:
        if use_latest:
            latest_task = self.store.get_latest_worked_task()
            if latest_task is None:
                raise RuntimeError("no worked task")
            return latest_task

        if task_ref is None:
            raise RuntimeError("task reference is required")
        return self.store.get_task(task_ref)

    def _resolve_planned_task(
        self,
        task_ref: str | None,
        position: int | None,
        day: str,
    ) -> TaskRecord:
        if task_ref is not None:
            task = self.store.get_task(task_ref)
        elif position is not None:
            task = self.store.get_backlog_task_for_date_by_position(day, position)
            if task is None:
                raise RuntimeError(f"no planned task at position {position}")
        else:
            raise RuntimeError("task reference is required")

        if task.state != "planned":
            raise RuntimeError("run only works for planned backlog tasks; use start or continue")
        return task

    @staticmethod
    def _assert_task_not_completed(task: TaskRecord, message: str) -> None:
        if task.state == "completed":
            raise RuntimeError(message)

    def _next_task_id(self, now: datetime) -> str:
        task_count = self.store.count_tasks_created_on_date(now.date().isoformat())
        return f"{now.strftime('%Y-%m%d')}-{task_count + 1:04d}"
