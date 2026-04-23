from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from pomo_cli.models import BacklogEntry, SessionRecord, SummaryTaskEntry, TaskRecord


class PomoStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_title TEXT NOT NULL,
                    state TEXT NOT NULL,
                    total_elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    estimate_minutes INTEGER,
                    priority TEXT,
                    source_parent_title TEXT,
                    position INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    planned_minutes INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                )
                """
            )
            self._ensure_parallel_sessions(connection)
            self._ensure_task_columns(connection)

    def _ensure_parallel_sessions(self, connection: sqlite3.Connection) -> None:
        connection.execute("DROP INDEX IF EXISTS sessions_single_active")

    def _ensure_task_columns(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("PRAGMA table_info(tasks)").fetchall()
        existing_columns = {row[1] for row in rows}
        for column_name, column_type in (
            ("estimate_minutes", "INTEGER"),
            ("priority", "TEXT"),
            ("source_parent_title", "TEXT"),
            ("position", "INTEGER"),
        ):
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE tasks ADD COLUMN {column_name} {column_type}"
                )

    def list_table_names(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        return [row[0] for row in rows]

    def insert_task(
        self,
        task_id: str,
        task_title: str,
        state: str,
        created_at: datetime,
    ) -> None:
        iso_now = created_at.isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, 0, ?, ?, NULL)
                """,
                (task_id, task_title, state, iso_now, iso_now),
            )

    def insert_session(
        self,
        session_id: str,
        task_id: str,
        planned_minutes: int,
        started_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (session_id, task_id, planned_minutes, started_at, ended_at, elapsed_seconds)
                VALUES (?, ?, ?, ?, NULL, 0)
                """,
                (session_id, task_id, planned_minutes, started_at.isoformat()),
            )

    def create_task_with_session(
        self,
        task_id: str,
        task_title: str,
        state: str,
        created_at: datetime,
        session_id: str,
        planned_minutes: int,
        started_at: datetime,
    ) -> None:
        iso_now = created_at.isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, 0, ?, ?, NULL)
                """,
                (task_id, task_title, state, iso_now, iso_now),
            )
            connection.execute(
                """
                INSERT INTO sessions (session_id, task_id, planned_minutes, started_at, ended_at, elapsed_seconds)
                VALUES (?, ?, ?, ?, NULL, 0)
                """,
                (session_id, task_id, planned_minutes, started_at.isoformat()),
            )

    def update_task_state_with_new_session(
        self,
        task_id: str,
        state: str,
        updated_at: datetime,
        completed_at: datetime | None,
        session_id: str,
        planned_minutes: int,
        started_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET state = ?, updated_at = ?, completed_at = ?
                WHERE task_id = ?
                """,
                (
                    state,
                    updated_at.isoformat(),
                    completed_at.isoformat() if completed_at else None,
                    task_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO sessions (session_id, task_id, planned_minutes, started_at, ended_at, elapsed_seconds)
                VALUES (?, ?, ?, ?, NULL, 0)
                """,
                (session_id, task_id, planned_minutes, started_at.isoformat()),
            )

    def get_task(self, task_id: str) -> TaskRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at,
                       estimate_minutes, priority, source_parent_title, position
                FROM tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._task_record_from_row(row)

    def get_active_session(self) -> SessionRecord | None:
        """Return the most recently started active session, or None."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, task_id, planned_minutes, started_at, ended_at, elapsed_seconds
                FROM sessions
                WHERE ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self._session_record_from_row(row)

    def get_active_sessions(self) -> list[SessionRecord]:
        """Return all active sessions, most recently started first."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, task_id, planned_minutes, started_at, ended_at, elapsed_seconds
                FROM sessions
                WHERE ended_at IS NULL
                ORDER BY started_at DESC
                """
            ).fetchall()
        return [self._session_record_from_row(row) for row in rows]

    def get_active_session_for_task(self, task_id: str) -> SessionRecord | None:
        """Return the open session for a specific task, or None."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, task_id, planned_minutes, started_at, ended_at, elapsed_seconds
                FROM sessions
                WHERE task_id = ? AND ended_at IS NULL
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._session_record_from_row(row)

    def task_exists(self, task_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return row is not None

    def count_tasks_created_on_date(self, day: str) -> int:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59.999999"
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE created_at BETWEEN ? AND ?
                """,
                (start, end),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def update_task_state(
        self,
        task_id: str,
        state: str,
        updated_at: datetime,
        completed_at: datetime | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET state = ?, updated_at = ?, completed_at = ?
                WHERE task_id = ?
                """,
                (
                    state,
                    updated_at.isoformat(),
                    completed_at.isoformat() if completed_at else None,
                    task_id,
                ),
            )

    def increment_task_elapsed(
        self,
        task_id: str,
        elapsed_seconds: int,
        updated_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET total_elapsed_seconds = total_elapsed_seconds + ?, updated_at = ?
                WHERE task_id = ?
                """,
                (elapsed_seconds, updated_at.isoformat(), task_id),
            )

    def create_planned_tasks(self, planned_tasks: list[dict[str, object]]) -> None:
        if not planned_tasks:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO tasks (
                    task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at,
                    estimate_minutes, priority, source_parent_title, position
                )
                VALUES (?, ?, 'planned', 0, ?, ?, NULL, ?, ?, ?, ?)
                """,
                [
                    (
                        task["task_id"],
                        task["task_title"],
                        task["created_at"].isoformat(),
                        task["created_at"].isoformat(),
                        task["estimate_minutes"],
                        task["priority"],
                        task["source_parent_title"],
                        task["position"],
                    )
                    for task in planned_tasks
                ],
            )

    def create_planned_task(
        self,
        task_id: str,
        task_title: str,
        created_at: datetime,
        estimate_minutes: int,
        priority: str,
        source_parent_title: str | None,
        position: int,
    ) -> None:
        self.create_planned_tasks(
            [
                {
                    "task_id": task_id,
                    "task_title": task_title,
                    "created_at": created_at,
                    "estimate_minutes": estimate_minutes,
                    "priority": priority,
                    "source_parent_title": source_parent_title,
                    "position": position,
                }
            ]
        )

    def close_session(
        self,
        session_id: str,
        ended_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET ended_at = ?, elapsed_seconds = ?
                WHERE session_id = ?
                """,
                (ended_at.isoformat(), elapsed_seconds, session_id),
            )

    def finalize_session(
        self,
        task_id: str,
        session_id: str,
        ended_at: datetime,
        elapsed_seconds: int,
        state: str,
        updated_at: datetime,
        completed_at: datetime | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET ended_at = ?, elapsed_seconds = ?
                WHERE session_id = ?
                """,
                (ended_at.isoformat(), elapsed_seconds, session_id),
            )
            connection.execute(
                """
                UPDATE tasks
                SET total_elapsed_seconds = total_elapsed_seconds + ?,
                    state = ?,
                    updated_at = ?,
                    completed_at = ?
                WHERE task_id = ?
                """,
                (
                    elapsed_seconds,
                    state,
                    updated_at.isoformat(),
                    completed_at.isoformat() if completed_at else None,
                    task_id,
                ),
            )

    def get_latest_task(self) -> TaskRecord | None:
        return self.get_latest_worked_task()

    def get_latest_worked_task(self) -> TaskRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT tasks.task_id, tasks.task_title, tasks.state, tasks.total_elapsed_seconds,
                       tasks.created_at, tasks.updated_at, tasks.completed_at,
                       tasks.estimate_minutes, tasks.priority, tasks.source_parent_title, tasks.position
                FROM tasks
                JOIN sessions ON sessions.task_id = tasks.task_id
                GROUP BY tasks.task_id, tasks.task_title, tasks.state, tasks.total_elapsed_seconds,
                         tasks.created_at, tasks.updated_at, tasks.completed_at,
                         tasks.estimate_minutes, tasks.priority, tasks.source_parent_title, tasks.position
                ORDER BY MAX(sessions.started_at) DESC, tasks.task_id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self._task_record_from_row(row)

    def get_latest_planned_task(self) -> TaskRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at,
                       estimate_minutes, priority, source_parent_title, position
                FROM tasks
                WHERE state = 'planned'
                ORDER BY created_at DESC, position DESC, task_id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self._task_record_from_row(row)

    def get_backlog_task_for_date_by_position(self, day: str, position: int) -> TaskRecord | None:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59.999999"
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at,
                       estimate_minutes, priority, source_parent_title, position
                FROM tasks
                WHERE created_at BETWEEN ? AND ? AND estimate_minutes IS NOT NULL AND position = ?
                ORDER BY task_id ASC
                LIMIT 1
                """,
                (start, end, position),
            ).fetchone()
        if row is None:
            return None
        return self._task_record_from_row(row)

    def get_latest_session_for_task(self, task_id: str) -> SessionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, task_id, planned_minutes, started_at, ended_at, elapsed_seconds
                FROM sessions
                WHERE task_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._session_record_from_row(row)

    def get_completed_tasks_for_date(self, day: str) -> list[TaskRecord]:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59.999999"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at,
                       estimate_minutes, priority, source_parent_title, position
                FROM tasks
                WHERE state = 'completed' AND completed_at BETWEEN ? AND ?
                ORDER BY completed_at ASC
                """,
                (start, end),
            ).fetchall()
        return [self._task_record_from_row(row) for row in rows]

    def list_task_time_entries_for_date(self, day: str) -> list[SummaryTaskEntry]:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59.999999"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT tasks.task_id, tasks.task_title, SUM(sessions.elapsed_seconds)
                FROM sessions
                JOIN tasks ON tasks.task_id = sessions.task_id
                WHERE sessions.ended_at BETWEEN ? AND ? AND sessions.elapsed_seconds > 0
                GROUP BY tasks.task_id, tasks.task_title
                ORDER BY MIN(sessions.ended_at) ASC
                """,
                (start, end),
            ).fetchall()
        return [
            SummaryTaskEntry(
                task_id=row[0],
                task_title=row[1],
                elapsed_seconds=row[2],
            )
            for row in rows
        ]

    def list_backlog_entries_for_date(self, day: str) -> list[BacklogEntry]:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59.999999"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT position, task_id, task_title, estimate_minutes, priority, source_parent_title, state
                FROM tasks
                WHERE created_at BETWEEN ? AND ? AND estimate_minutes IS NOT NULL
                ORDER BY position ASC, task_id ASC
                """,
                (start, end),
            ).fetchall()
        return [
            BacklogEntry(
                position=row[0],
                task_id=row[1],
                task_title=row[2],
                estimate_minutes=row[3],
                priority=row[4],
                source_parent_title=row[5],
                state=row[6],
            )
            for row in rows
        ]

    def count_backlog_entries_for_date(self, day: str) -> int:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59.999999"
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE created_at BETWEEN ? AND ? AND estimate_minutes IS NOT NULL
                """,
                (start, end),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    def count_completed_tasks_for_date(self, day: str) -> int:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59.999999"
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM tasks
                WHERE completed_at BETWEEN ? AND ?
                """,
                (start, end),
            ).fetchone()
        return int(row[0]) if row is not None else 0

    @staticmethod
    def _session_record_from_row(row: tuple[object, ...]) -> SessionRecord:
        return SessionRecord(
            session_id=row[0],
            task_id=row[1],
            planned_minutes=row[2],
            started_at=datetime.fromisoformat(row[3]),
            ended_at=datetime.fromisoformat(row[4]) if row[4] else None,
            elapsed_seconds=row[5],
        )

    @staticmethod
    def _task_record_from_row(row: tuple[object, ...]) -> TaskRecord:
        return TaskRecord(
            task_id=row[0],
            task_title=row[1],
            state=row[2],
            total_elapsed_seconds=row[3],
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]),
            completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
            estimate_minutes=row[7],
            priority=row[8],
            source_parent_title=row[9],
            position=row[10],
        )
