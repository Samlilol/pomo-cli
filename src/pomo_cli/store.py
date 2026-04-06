from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from pomo_cli.models import SessionRecord, TaskRecord


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
                    completed_at TEXT
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
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS sessions_single_active
                ON sessions (1)
                WHERE ended_at IS NULL
                """
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
                SELECT task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at
                FROM tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return TaskRecord(
            task_id=row[0],
            task_title=row[1],
            state=row[2],
            total_elapsed_seconds=row[3],
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]),
            completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
        )

    def get_active_session(self) -> SessionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, task_id, planned_minutes, started_at, ended_at, elapsed_seconds
                FROM sessions
                WHERE ended_at IS NULL
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return SessionRecord(
            session_id=row[0],
            task_id=row[1],
            planned_minutes=row[2],
            started_at=datetime.fromisoformat(row[3]),
            ended_at=datetime.fromisoformat(row[4]) if row[4] else None,
            elapsed_seconds=row[5],
        )

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
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at
                FROM tasks
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return TaskRecord(
            task_id=row[0],
            task_title=row[1],
            state=row[2],
            total_elapsed_seconds=row[3],
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]),
            completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
        )

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
        return SessionRecord(
            session_id=row[0],
            task_id=row[1],
            planned_minutes=row[2],
            started_at=datetime.fromisoformat(row[3]),
            ended_at=datetime.fromisoformat(row[4]) if row[4] else None,
            elapsed_seconds=row[5],
        )

    def get_completed_tasks_for_date(self, day: str) -> list[TaskRecord]:
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59.999999"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT task_id, task_title, state, total_elapsed_seconds, created_at, updated_at, completed_at
                FROM tasks
                WHERE state = 'completed' AND completed_at BETWEEN ? AND ?
                ORDER BY completed_at ASC
                """,
                (start, end),
            ).fetchall()
        return [
            TaskRecord(
                task_id=row[0],
                task_title=row[1],
                state=row[2],
                total_elapsed_seconds=row[3],
                created_at=datetime.fromisoformat(row[4]),
                updated_at=datetime.fromisoformat(row[5]),
                completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
            )
            for row in rows
        ]
