import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import sqlite3

from pomo_cli.store import PomoStore


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pomo.db"
        self.store = PomoStore(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initialize_creates_tasks_and_sessions_tables(self) -> None:
        self.store.initialize()

        table_names = self.store.list_table_names()

        self.assertIn("tasks", table_names)
        self.assertIn("sessions", table_names)

    def test_insert_task_and_session_round_trip(self) -> None:
        self.store.initialize()
        self.store.insert_task(
            task_id="task-1",
            task_title="write 500-word essay",
            state="running",
            created_at=datetime(2026, 4, 2, 10, 0, 0),
        )
        self.store.insert_session(
            session_id="session-1",
            task_id="task-1",
            planned_minutes=30,
            started_at=datetime(2026, 4, 2, 10, 0, 0),
        )

        task = self.store.get_task("task-1")
        session = self.store.get_active_session()

        self.assertEqual(task.task_id, "task-1")
        self.assertEqual(task.state, "running")
        self.assertEqual(session.session_id, "session-1")
        self.assertEqual(session.planned_minutes, 30)

    def test_insert_session_rejects_missing_task(self) -> None:
        self.store.initialize()

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_session(
                session_id="session-1",
                task_id="missing-task",
                planned_minutes=30,
                started_at=datetime(2026, 4, 2, 10, 0, 0),
            )

    def test_insert_session_rejects_second_active_session(self) -> None:
        self.store.initialize()
        self.store.insert_task(
            task_id="task-1",
            task_title="write 500-word essay",
            state="running",
            created_at=datetime(2026, 4, 2, 10, 0, 0),
        )
        self.store.insert_task(
            task_id="task-2",
            task_title="review notes",
            state="running",
            created_at=datetime(2026, 4, 2, 10, 1, 0),
        )
        self.store.insert_session(
            session_id="session-1",
            task_id="task-1",
            planned_minutes=30,
            started_at=datetime(2026, 4, 2, 10, 0, 0),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_session(
                session_id="session-2",
                task_id="task-2",
                planned_minutes=25,
                started_at=datetime(2026, 4, 2, 10, 2, 0),
            )

    def test_list_task_time_entries_for_date_returns_finalized_session_totals(self) -> None:
        self.store.initialize()
        self.store.create_task_with_session(
            task_id="2026-0604-0001",
            task_title="write draft",
            state="running",
            created_at=datetime(2026, 4, 6, 9, 0, 0),
            session_id="session-1",
            planned_minutes=25,
            started_at=datetime(2026, 4, 6, 9, 0, 0),
        )
        self.store.finalize_session(
            task_id="2026-0604-0001",
            session_id="session-1",
            ended_at=datetime(2026, 4, 6, 9, 25, 0),
            elapsed_seconds=25 * 60,
            state="session_closed",
            updated_at=datetime(2026, 4, 6, 9, 25, 0),
            completed_at=None,
        )

        entries = self.store.list_task_time_entries_for_date("2026-04-06")

        self.assertEqual(
            [(entry.task_id, entry.task_title, entry.elapsed_seconds) for entry in entries],
            [("2026-0604-0001", "write draft", 25 * 60)],
        )


if __name__ == "__main__":
    unittest.main()
