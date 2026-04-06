import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import sqlite3

from pomo_cli.service import PomoService
from pomo_cli.store import PomoStore


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pomo.db"
        self.store = PomoStore(self.db_path)
        self.store.initialize()
        self.service = PomoService(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_start_new_task_creates_running_task_and_session(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=30,
            now=datetime(2026, 4, 2, 14, 0, 0),
        )

        self.assertEqual(status.state, "running")
        self.assertEqual(status.task_title, "write 500-word essay")
        self.assertEqual(status.planned_minutes, 30)

    def test_start_new_task_uses_day_based_task_id_sequence(self) -> None:
        first = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=25,
            now=datetime(2026, 4, 6, 9, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 6, 9, 25, 0))

        second = self.service.start_new_task(
            task_title="review notes",
            planned_minutes=15,
            now=datetime(2026, 4, 6, 10, 0, 0),
        )

        self.assertEqual(first.task_id, "2026-0604-0001")
        self.assertEqual(second.task_id, "2026-0604-0002")

    def test_start_new_task_resets_day_based_sequence_on_a_new_day(self) -> None:
        first = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=25,
            now=datetime(2026, 4, 6, 9, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 6, 9, 25, 0))

        second = self.service.start_new_task(
            task_title="plan tomorrow",
            planned_minutes=10,
            now=datetime(2026, 4, 7, 9, 0, 0),
        )

        self.assertEqual(first.task_id, "2026-0604-0001")
        self.assertEqual(second.task_id, "2026-0704-0001")

    def test_close_running_session_moves_task_to_session_closed(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=30,
            now=datetime(2026, 4, 2, 14, 0, 0),
        )

        closed = self.service.close_active_session(
            now=datetime(2026, 4, 2, 14, 12, 0),
        )

        self.assertEqual(closed.task_id, status.task_id)
        self.assertEqual(closed.state, "session_closed")
        self.assertEqual(closed.total_elapsed_seconds, 12 * 60)

    def test_complete_after_session_closed_does_not_double_count(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=30,
            now=datetime(2026, 4, 2, 14, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 2, 14, 12, 0))

        completed = self.service.complete_task(
            task_ref=status.task_id,
            use_latest=False,
            now=datetime(2026, 4, 2, 14, 13, 0),
        )

        self.assertEqual(completed.state, "completed")
        self.assertEqual(completed.total_elapsed_seconds, 12 * 60)
        self.assertEqual(completed.completed_at, datetime(2026, 4, 2, 14, 13, 0))

    def test_summary_uses_completed_at_local_date(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=30,
            now=datetime(2026, 4, 2, 23, 50, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 3, 0, 5, 0))
        self.service.complete_task(
            task_ref=status.task_id,
            use_latest=False,
            now=datetime(2026, 4, 3, 0, 10, 0),
        )

        summary = self.service.summary_for_date(day="2026-04-03")

        self.assertEqual(summary.tasks_completed, 1)
        self.assertEqual(summary.total_time_spent_today, 15 * 60)

    def test_latest_resolves_most_recent_task(self) -> None:
        first = self.service.start_new_task(
            task_title="write intro",
            planned_minutes=25,
            now=datetime(2026, 4, 2, 10, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 2, 10, 25, 0))
        second = self.service.start_existing_task(
            task_ref=first.task_id,
            use_latest=False,
            planned_minutes=30,
            now=datetime(2026, 4, 2, 11, 0, 0),
        )

        completed = self.service.complete_task(
            task_ref=None,
            use_latest=True,
            now=datetime(2026, 4, 2, 11, 10, 0),
        )

        self.assertEqual(completed.task_id, second.task_id)
        self.assertEqual(completed.total_elapsed_seconds, (25 + 10) * 60)

    def test_start_new_task_rolls_back_if_session_insert_fails(self) -> None:
        with self.store._connect() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_session_insert
                BEFORE INSERT ON sessions
                BEGIN
                    SELECT RAISE(FAIL, 'simulated session insert failure');
                END;
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.service.start_new_task(
                task_title="write 500-word essay",
                planned_minutes=30,
                now=datetime(2026, 4, 2, 14, 0, 0),
            )

        self.assertIsNone(self.store.get_latest_task())
        self.assertIsNone(self.store.get_active_session())

    def test_summary_keeps_tasks_with_duplicate_titles(self) -> None:
        first = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=25,
            now=datetime(2026, 4, 2, 9, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 2, 9, 25, 0))
        self.service.complete_task(
            task_ref=first.task_id,
            use_latest=False,
            now=datetime(2026, 4, 2, 9, 30, 0),
        )

        second = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=15,
            now=datetime(2026, 4, 2, 10, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 2, 10, 15, 0))
        self.service.complete_task(
            task_ref=second.task_id,
            use_latest=False,
            now=datetime(2026, 4, 2, 10, 20, 0),
        )

        summary = self.service.summary_for_date(day="2026-04-02")

        self.assertEqual(summary.tasks_completed, 2)
        self.assertEqual(summary.total_time_spent_today, 40 * 60)
        self.assertEqual(summary.time_spent_by_task, {"write 500-word essay": 40 * 60})

    def test_summary_reports_worked_today_and_completed_today_separately(self) -> None:
        first = self.service.start_new_task(
            task_title="write draft",
            planned_minutes=25,
            now=datetime(2026, 4, 6, 9, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 6, 9, 25, 0))

        second = self.service.start_new_task(
            task_title="review notes",
            planned_minutes=15,
            now=datetime(2026, 4, 6, 10, 0, 0),
        )
        self.service.complete_task(
            task_ref=second.task_id,
            use_latest=False,
            now=datetime(2026, 4, 6, 10, 15, 0),
        )

        summary = self.service.summary_for_date("2026-04-06")

        self.assertEqual(summary.tasks_worked_on_today, 2)
        self.assertEqual(summary.tasks_completed_today, 1)
        self.assertEqual(summary.total_time_spent_today, 40 * 60)
        self.assertEqual(
            [(entry.task_id, entry.task_title, entry.elapsed_seconds) for entry in summary.task_entries],
            [
                (first.task_id, "write draft", 25 * 60),
                (second.task_id, "review notes", 15 * 60),
            ],
        )

    def test_start_existing_task_rejects_completed_task(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=25,
            now=datetime(2026, 4, 2, 9, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 2, 9, 25, 0))
        self.service.complete_task(
            task_ref=status.task_id,
            use_latest=False,
            now=datetime(2026, 4, 2, 9, 30, 0),
        )

        with self.assertRaisesRegex(RuntimeError, "cannot start a completed task"):
            self.service.start_existing_task(
                task_ref=status.task_id,
                use_latest=False,
                planned_minutes=15,
                now=datetime(2026, 4, 2, 10, 0, 0),
            )

    def test_complete_task_rejects_completed_task(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=25,
            now=datetime(2026, 4, 2, 9, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 2, 9, 25, 0))
        self.service.complete_task(
            task_ref=status.task_id,
            use_latest=False,
            now=datetime(2026, 4, 2, 9, 30, 0),
        )

        with self.assertRaisesRegex(RuntimeError, "task is already completed"):
            self.service.complete_task(
                task_ref=status.task_id,
                use_latest=False,
                now=datetime(2026, 4, 2, 10, 0, 0),
            )


if __name__ == "__main__":
    unittest.main()
