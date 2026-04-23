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

    def test_insert_session_allows_multiple_active_sessions(self) -> None:
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
        self.store.insert_session(
            session_id="session-2",
            task_id="task-2",
            planned_minutes=25,
            started_at=datetime(2026, 4, 2, 10, 2, 0),
        )

        sessions = self.store.get_active_sessions()
        self.assertEqual(len(sessions), 2)

    def test_get_active_sessions_empty_returns_empty_list(self) -> None:
        self.store.initialize()

        sessions = self.store.get_active_sessions()

        self.assertEqual(sessions, [])

    def test_get_active_sessions_returns_all_open_sessions_most_recent_first(self) -> None:
        self.store.initialize()
        self.store.insert_task("t1", "task one", "running", datetime(2026, 4, 2, 10, 0, 0))
        self.store.insert_task("t2", "task two", "running", datetime(2026, 4, 2, 10, 1, 0))
        self.store.insert_session("s1", "t1", 25, datetime(2026, 4, 2, 10, 0, 0))
        self.store.insert_session("s2", "t2", 30, datetime(2026, 4, 2, 10, 5, 0))

        sessions = self.store.get_active_sessions()

        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0].session_id, "s2")  # started later
        self.assertEqual(sessions[1].session_id, "s1")

    def test_get_active_session_for_task_returns_open_session(self) -> None:
        self.store.initialize()
        self.store.insert_task("t1", "task one", "running", datetime(2026, 4, 2, 10, 0, 0))
        self.store.insert_task("t2", "task two", "running", datetime(2026, 4, 2, 10, 1, 0))
        self.store.insert_session("s1", "t1", 25, datetime(2026, 4, 2, 10, 0, 0))
        self.store.insert_session("s2", "t2", 30, datetime(2026, 4, 2, 10, 5, 0))

        found = self.store.get_active_session_for_task("t1")
        missing = self.store.get_active_session_for_task("t-unknown")

        self.assertIsNotNone(found)
        self.assertEqual(found.session_id, "s1")
        self.assertIsNone(missing)

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

    def test_create_planned_tasks_round_trip_and_backlog_order(self) -> None:
        self.store.initialize()
        self.store.create_planned_tasks(
            [
                {
                    "task_id": "2026-1004-0001",
                    "task_title": "outline launch email",
                    "created_at": datetime(2026, 4, 10, 9, 0, 0),
                    "estimate_minutes": 15,
                    "priority": "high",
                    "source_parent_title": "Launch prep",
                    "position": 1,
                },
                {
                    "task_id": "2026-1004-0002",
                    "task_title": "draft changelog",
                    "created_at": datetime(2026, 4, 10, 9, 0, 0),
                    "estimate_minutes": 10,
                    "priority": "medium",
                    "source_parent_title": "Launch prep",
                    "position": 2,
                },
            ]
        )

        first_task = self.store.get_task("2026-1004-0001")
        entries = self.store.list_backlog_entries_for_date("2026-04-10")
        latest_planned = self.store.get_latest_planned_task()
        latest_worked = self.store.get_latest_worked_task()
        first_session = self.store.get_latest_session_for_task("2026-1004-0001")

        self.assertEqual(first_task.state, "planned")
        self.assertEqual(first_task.estimate_minutes, 15)
        self.assertEqual(first_task.priority, "high")
        self.assertEqual(first_task.source_parent_title, "Launch prep")
        self.assertEqual(first_task.position, 1)
        self.assertIsNone(first_session)
        self.assertIsNone(latest_worked)
        self.assertIsNotNone(latest_planned)
        self.assertEqual(latest_planned.task_id, "2026-1004-0002")
        self.assertEqual(
            [
                (
                    entry.position,
                    entry.task_id,
                    entry.task_title,
                    entry.estimate_minutes,
                    entry.priority,
                    entry.source_parent_title,
                    entry.state,
                )
                for entry in entries
            ],
            [
                (1, "2026-1004-0001", "outline launch email", 15, "high", "Launch prep", "planned"),
                (2, "2026-1004-0002", "draft changelog", 10, "medium", "Launch prep", "planned"),
            ],
        )

    def test_get_latest_worked_task_ignores_planned_backlog_rows(self) -> None:
        self.store.initialize()
        self.store.create_task_with_session(
            task_id="2026-1004-0001",
            task_title="write draft",
            state="running",
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            session_id="session-1",
            planned_minutes=25,
            started_at=datetime(2026, 4, 10, 8, 0, 0),
        )
        self.store.finalize_session(
            task_id="2026-1004-0001",
            session_id="session-1",
            ended_at=datetime(2026, 4, 10, 8, 25, 0),
            elapsed_seconds=25 * 60,
            state="session_closed",
            updated_at=datetime(2026, 4, 10, 8, 25, 0),
            completed_at=None,
        )
        self.store.create_planned_tasks(
            [
                {
                    "task_id": "2026-1004-0002",
                    "task_title": "outline launch email",
                    "created_at": datetime(2026, 4, 10, 9, 0, 0),
                    "estimate_minutes": 15,
                    "priority": "high",
                    "source_parent_title": "Launch prep",
                    "position": 1,
                }
            ]
        )

        latest_worked = self.store.get_latest_worked_task()

        self.assertIsNotNone(latest_worked)
        self.assertEqual(latest_worked.task_id, "2026-1004-0001")

    def test_get_backlog_task_for_date_by_position_returns_matching_task(self) -> None:
        self.store.initialize()
        self.store.create_planned_tasks(
            [
                {
                    "task_id": "2026-1004-0001",
                    "task_title": "outline launch email",
                    "created_at": datetime(2026, 4, 10, 9, 0, 0),
                    "estimate_minutes": 15,
                    "priority": "high",
                    "source_parent_title": "Launch prep",
                    "position": 1,
                },
                {
                    "task_id": "2026-1004-0002",
                    "task_title": "draft changelog",
                    "created_at": datetime(2026, 4, 10, 9, 0, 0),
                    "estimate_minutes": 10,
                    "priority": "medium",
                    "source_parent_title": "Launch prep",
                    "position": 2,
                },
            ]
        )

        first = self.store.get_backlog_task_for_date_by_position("2026-04-10", 1)
        second = self.store.get_backlog_task_for_date_by_position("2026-04-10", 2)
        missing = self.store.get_backlog_task_for_date_by_position("2026-04-10", 3)

        self.assertIsNotNone(first)
        self.assertEqual(first.task_id, "2026-1004-0001")
        self.assertIsNotNone(second)
        self.assertEqual(second.task_id, "2026-1004-0002")
        self.assertIsNone(missing)


if __name__ == "__main__":
    unittest.main()
