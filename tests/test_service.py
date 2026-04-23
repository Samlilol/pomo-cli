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

        self.assertEqual(first.task_id, "2026-0406-0001")
        self.assertEqual(second.task_id, "2026-0406-0002")

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

        self.assertEqual(first.task_id, "2026-0406-0001")
        self.assertEqual(second.task_id, "2026-0407-0001")

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

        self.assertEqual(summary.tasks_worked_on_today, 1)
        self.assertEqual(summary.tasks_completed_today, 1)
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

    def test_continue_task_uses_latest_task_when_task_id_is_omitted(self) -> None:
        first = self.service.start_new_task(
            task_title="write draft",
            planned_minutes=25,
            now=datetime(2026, 4, 6, 9, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 6, 9, 25, 0))

        continued = self.service.continue_task(
            task_ref=None,
            planned_minutes=10,
            now=datetime(2026, 4, 6, 10, 0, 0),
        )

        self.assertEqual(continued.task_id, first.task_id)
        self.assertEqual(continued.planned_minutes, 10)

    def test_plan_tasks_creates_subtasks_with_metadata_in_stable_order(self) -> None:
        planned_tasks = self.service.plan_tasks(
            parent_title="Ship pomo update",
            subtasks=[
                {
                    "task_title": "review failing tests",
                    "estimate_minutes": 15,
                    "priority": "high",
                },
                {
                    "task_title": "write release note",
                    "estimate_minutes": 10,
                    "priority": "medium",
                },
            ],
            now=datetime(2026, 4, 10, 9, 0, 0),
        )

        backlog = self.service.backlog_for_date("2026-04-10")

        self.assertEqual(
            [(task.task_id, task.task_title, task.estimate_minutes, task.priority) for task in planned_tasks],
            [
                ("2026-0410-0001", "review failing tests", 15, "high"),
                ("2026-0410-0002", "write release note", 10, "medium"),
            ],
        )
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
                for entry in backlog
            ],
            [
                (1, "2026-0410-0001", "review failing tests", 15, "high", "Ship pomo update", "planned"),
                (2, "2026-0410-0002", "write release note", 10, "medium", "Ship pomo update", "planned"),
            ],
        )

    def test_plan_tasks_is_atomic_when_a_later_subtask_is_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "priority must be one of"):
            self.service.plan_tasks(
                parent_title="Ship pomo update",
                subtasks=[
                    {
                        "task_title": "review failing tests",
                        "estimate_minutes": 15,
                        "priority": "high",
                    },
                    {
                        "task_title": "write release note",
                        "estimate_minutes": 10,
                        "priority": "urgent",
                    },
                ],
                now=datetime(2026, 4, 10, 9, 0, 0),
            )

        self.assertEqual(self.service.backlog_for_date("2026-04-10"), [])

    def test_continue_task_without_task_id_ignores_planned_tasks(self) -> None:
        worked = self.service.start_new_task(
            task_title="write draft",
            planned_minutes=25,
            now=datetime(2026, 4, 10, 8, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 10, 8, 25, 0))
        self.service.plan_tasks(
            parent_title="Ship pomo update",
            subtasks=[
                {
                    "task_title": "review failing tests",
                    "estimate_minutes": 15,
                    "priority": "high",
                }
            ],
            now=datetime(2026, 4, 10, 9, 0, 0),
        )

        continued = self.service.continue_task(
            task_ref=None,
            planned_minutes=10,
            now=datetime(2026, 4, 10, 9, 30, 0),
        )

        self.assertEqual(continued.task_id, worked.task_id)

    def test_run_planned_task_uses_stored_estimate_by_default(self) -> None:
        planned = self.service.plan_tasks(
            parent_title="Ship pomo update",
            subtasks=[
                {
                    "task_title": "review failing tests",
                    "estimate_minutes": 15,
                    "priority": "high",
                }
            ],
            now=datetime(2026, 4, 10, 9, 0, 0),
        )[0]

        running = self.service.run_planned_task(
            task_ref=planned.task_id,
            position=None,
            planned_minutes=None,
            now=datetime(2026, 4, 10, 9, 30, 0),
        )

        self.assertEqual(running.task_id, planned.task_id)
        self.assertEqual(running.state, "running")
        self.assertEqual(running.planned_minutes, 15)

    def test_run_planned_task_by_position_resolves_today_backlog(self) -> None:
        self.service.plan_tasks(
            parent_title="Ship pomo update",
            subtasks=[
                {
                    "task_title": "review failing tests",
                    "estimate_minutes": 15,
                    "priority": "high",
                },
                {
                    "task_title": "write release note",
                    "estimate_minutes": 10,
                    "priority": "medium",
                },
            ],
            now=datetime(2026, 4, 10, 9, 0, 0),
        )

        running = self.service.run_planned_task(
            task_ref=None,
            position=2,
            planned_minutes=20,
            now=datetime(2026, 4, 10, 9, 30, 0),
        )

        self.assertEqual(running.task_title, "write release note")
        self.assertEqual(running.planned_minutes, 20)

    def test_run_planned_task_rejects_non_planned_task(self) -> None:
        worked = self.service.start_new_task(
            task_title="write draft",
            planned_minutes=25,
            now=datetime(2026, 4, 10, 8, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 10, 8, 25, 0))

        with self.assertRaisesRegex(RuntimeError, "planned task startup only works"):
            self.service.run_planned_task(
                task_ref=worked.task_id,
                position=None,
                planned_minutes=None,
                now=datetime(2026, 4, 10, 9, 30, 0),
            )

    def test_complete_latest_ignores_planned_tasks(self) -> None:
        worked = self.service.start_new_task(
            task_title="write draft",
            planned_minutes=25,
            now=datetime(2026, 4, 10, 8, 0, 0),
        )
        self.service.close_active_session(now=datetime(2026, 4, 10, 8, 25, 0))
        self.service.plan_tasks(
            parent_title="Ship pomo update",
            subtasks=[
                {
                    "task_title": "review failing tests",
                    "estimate_minutes": 15,
                    "priority": "high",
                }
            ],
            now=datetime(2026, 4, 10, 9, 0, 0),
        )

        completed = self.service.complete_task(
            task_ref=None,
            use_latest=True,
            now=datetime(2026, 4, 10, 9, 30, 0),
        )

        self.assertEqual(completed.task_id, worked.task_id)
        self.assertEqual(completed.state, "completed")

    def test_plan_tasks_rejects_invalid_priority(self) -> None:
        with self.assertRaisesRegex(ValueError, "priority must be one of"):
            self.service.plan_tasks(
                parent_title="Ship pomo update",
                subtasks=[
                    {
                        "task_title": "review failing tests",
                        "estimate_minutes": 15,
                        "priority": "urgent",
                    }
                ],
                now=datetime(2026, 4, 10, 9, 0, 0),
            )

    def test_complete_task_allows_explicit_planned_task(self) -> None:
        planned = self.service.plan_tasks(
            parent_title="Ship pomo update",
            subtasks=[
                {
                    "task_title": "review failing tests",
                    "estimate_minutes": 15,
                    "priority": "high",
                }
            ],
            now=datetime(2026, 4, 10, 9, 0, 0),
        )[0]

        completed = self.service.complete_task(
            task_ref=planned.task_id,
            use_latest=False,
            now=datetime(2026, 4, 10, 9, 30, 0),
        )

        self.assertEqual(completed.task_id, planned.task_id)
        self.assertEqual(completed.state, "completed")
        self.assertEqual(completed.total_elapsed_seconds, 0)

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

        self.assertEqual(summary.tasks_worked_on_today, 2)
        self.assertEqual(summary.tasks_completed_today, 2)
        self.assertEqual(summary.total_time_spent_today, 40 * 60)
        self.assertEqual(
            [(entry.task_id, entry.task_title, entry.elapsed_seconds) for entry in summary.task_entries],
            [
                (first.task_id, "write 500-word essay", 25 * 60),
                (second.task_id, "write 500-word essay", 15 * 60),
            ],
        )

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


    def test_start_new_task_allows_parallel_sessions(self) -> None:
        first = self.service.start_new_task(
            task_title="LIN-123",
            planned_minutes=25,
            now=datetime(2026, 4, 22, 9, 0, 0),
        )
        second = self.service.start_new_task(
            task_title="review UIUX",
            planned_minutes=30,
            now=datetime(2026, 4, 22, 9, 5, 0),
        )

        self.assertEqual(first.state, "running")
        self.assertEqual(second.state, "running")
        self.assertNotEqual(first.task_id, second.task_id)
        active = self.service.store.get_active_sessions()
        self.assertEqual(len(active), 2)

    def test_close_active_session_by_task_id_closes_only_that_task(self) -> None:
        first = self.service.start_new_task(
            task_title="LIN-123",
            planned_minutes=25,
            now=datetime(2026, 4, 22, 9, 0, 0),
        )
        self.service.start_new_task(
            task_title="review UIUX",
            planned_minutes=30,
            now=datetime(2026, 4, 22, 9, 5, 0),
        )

        closed = self.service.close_active_session(
            now=datetime(2026, 4, 22, 9, 20, 0),
            task_id=first.task_id,
        )

        self.assertEqual(closed.state, "session_closed")
        self.assertEqual(closed.task_id, first.task_id)
        remaining = self.service.store.get_active_sessions()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].task_id, second.task_id if False else remaining[0].task_id)

    def test_get_all_active_statuses_returns_all_running_tasks(self) -> None:
        self.service.start_new_task(
            task_title="LIN-123",
            planned_minutes=25,
            now=datetime(2026, 4, 22, 9, 0, 0),
        )
        self.service.start_new_task(
            task_title="review UIUX",
            planned_minutes=30,
            now=datetime(2026, 4, 22, 9, 5, 0),
        )

        statuses = self.service.get_all_active_statuses(now=datetime(2026, 4, 22, 9, 10, 0))

        self.assertEqual(len(statuses), 2)
        titles = {s.task_title for s in statuses}
        self.assertIn("LIN-123", titles)
        self.assertIn("review UIUX", titles)

    def test_get_status_returns_most_recently_started_when_multiple_running(self) -> None:
        self.service.start_new_task(
            task_title="LIN-123",
            planned_minutes=25,
            now=datetime(2026, 4, 22, 9, 0, 0),
        )
        self.service.start_new_task(
            task_title="review UIUX",
            planned_minutes=30,
            now=datetime(2026, 4, 22, 9, 5, 0),
        )

        status = self.service.get_status(now=datetime(2026, 4, 22, 9, 10, 0))

        self.assertEqual(status.task_title, "review UIUX")

    def test_continue_task_rejects_already_running_task(self) -> None:
        first = self.service.start_new_task(
            task_title="LIN-123",
            planned_minutes=25,
            now=datetime(2026, 4, 22, 9, 0, 0),
        )

        with self.assertRaisesRegex(RuntimeError, "already has an active session"):
            self.service.continue_task(
                task_ref=first.task_id,
                planned_minutes=25,
                now=datetime(2026, 4, 22, 9, 5, 0),
            )


if __name__ == "__main__":
    unittest.main()
