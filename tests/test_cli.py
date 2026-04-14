import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from pomo_cli.cli import build_parser, format_backlog, format_status, format_summary, main
from pomo_cli.models import BacklogEntry, SummaryTaskEntry
from pomo_cli.service import PomoService, StatusPayload, SummaryPayload
from pomo_cli.store import PomoStore


ROOT = Path(__file__).resolve().parents[1]


class CliSmokeTests(unittest.TestCase):
    def test_help_lists_expected_commands(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "pomo_cli", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("start", result.stdout)
        self.assertIn("continue", result.stdout)
        self.assertIn("complete", result.stdout)
        self.assertIn("watch", result.stdout)
        self.assertIn("status", result.stdout)
        self.assertIn("summary", result.stdout)

    def test_status_parses(self) -> None:
        args = build_parser().parse_args(["status"])

        self.assertEqual(args.command, "status")

    def test_summary_parses(self) -> None:
        args = build_parser().parse_args(["summary"])

        self.assertEqual(args.command, "summary")

    def test_backlog_parses(self) -> None:
        args = build_parser().parse_args(["backlog"])

        self.assertEqual(args.command, "backlog")

    def test_plan_parses(self) -> None:
        args = build_parser().parse_args(["plan", "--file", "plan.json"])

        self.assertEqual(args.command, "plan")
        self.assertEqual(args.file, "plan.json")

    def test_run_with_task_id_parses(self) -> None:
        args = build_parser().parse_args(["run", "--task-id", "2026-0604-0001"])

        self.assertEqual(args.command, "run")
        self.assertEqual(args.task_id, "2026-0604-0001")
        self.assertIsNone(args.position)
        self.assertIsNone(args.minutes)

    def test_run_with_position_parses(self) -> None:
        args = build_parser().parse_args(["run", "--position", "1", "--minutes", "15"])

        self.assertEqual(args.command, "run")
        self.assertEqual(args.position, 1)
        self.assertIsNone(args.task_id)
        self.assertEqual(args.minutes, 15)

    def test_watch_parses(self) -> None:
        args = build_parser().parse_args(["watch"])

        self.assertEqual(args.command, "watch")

    def test_start_with_task_parses(self) -> None:
        args = build_parser().parse_args(["start", "--task", "Write tests", "--minutes", "25"])

        self.assertEqual(args.command, "start")
        self.assertEqual(args.task, "Write tests")
        self.assertEqual(args.minutes, 25)

    def test_continue_without_task_id_parses(self) -> None:
        args = build_parser().parse_args(["continue", "--minutes", "25"])

        self.assertEqual(args.command, "continue")
        self.assertIsNone(args.task_id)
        self.assertEqual(args.minutes, 25)

    def test_continue_with_task_id_parses(self) -> None:
        args = build_parser().parse_args(["continue", "--task-id", "2026-0604-0001", "--minutes", "25"])

        self.assertEqual(args.command, "continue")
        self.assertEqual(args.task_id, "2026-0604-0001")
        self.assertEqual(args.minutes, 25)

    def test_complete_with_task_id_parses(self) -> None:
        args = build_parser().parse_args(["complete", "--task-id", "123"])

        self.assertEqual(args.command, "complete")
        self.assertEqual(args.task_id, "123")
        self.assertFalse(args.latest)

    def test_complete_latest_parses(self) -> None:
        args = build_parser().parse_args(["complete", "--latest"])

        self.assertEqual(args.command, "complete")
        self.assertIsNone(args.task_id)
        self.assertTrue(args.latest)

    def test_start_rejects_missing_selector(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start", "--minutes", "25"])

    def test_start_rejects_task_id_selector(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start", "--task-id", "123", "--minutes", "25"])

    def test_start_rejects_zero_minutes(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start", "--task", "Write tests", "--minutes", "0"])

    def test_start_rejects_negative_minutes(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start", "--task", "Write tests", "--minutes", "-5"])

    def test_run_rejects_missing_selector(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["run"])

    def test_run_rejects_multiple_selectors(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["run", "--task-id", "123", "--position", "1"])

    def test_run_rejects_zero_minutes(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["run", "--task-id", "123", "--minutes", "0"])

    def test_complete_rejects_multiple_selectors(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["complete", "--task-id", "123", "--latest"])

    def test_format_status_renders_timestamps_to_seconds(self) -> None:
        rendered = format_status(
            StatusPayload(
                state="completed",
                task_id="ux-smoke-task",
                task_title="ux smoke task",
                planned_minutes=1,
                starts_at=datetime(2026, 4, 3, 22, 10, 34, 635189),
                ends_at=datetime(2026, 4, 3, 22, 11, 34, 635189),
                remaining_seconds=0,
                total_elapsed_seconds=10,
                completed_at=datetime(2026, 4, 3, 22, 10, 45, 121273),
            )
        )

        self.assertIn("starts_at: 2026-04-03 22:10:34", rendered)
        self.assertIn("scheduled_end_at: 2026-04-03 22:11:34", rendered)
        self.assertIn("completed_at: 2026-04-03 22:10:45", rendered)
        self.assertNotIn(".635189", rendered)
        self.assertNotIn(".121273", rendered)
        self.assertNotIn("T22:10:34", rendered)

    def test_format_status_omits_remaining(self) -> None:
        rendered = format_status(
            StatusPayload(
                state="running",
                task_id="2026-0604-0001",
                task_title="write draft",
                planned_minutes=25,
                starts_at=datetime(2026, 4, 6, 9, 0, 0),
                ends_at=datetime(2026, 4, 6, 9, 25, 0),
                remaining_seconds=10,
                total_elapsed_seconds=0,
                completed_at=None,
            )
        )

        self.assertNotIn("remaining:", rendered)

    def test_format_summary_renders_worked_and_completed_counts(self) -> None:
        rendered = format_summary(
            SummaryPayload(
                tasks_worked_on_today=2,
                tasks_completed_today=1,
                total_time_spent_today=40 * 60,
                task_entries=[
                    SummaryTaskEntry(
                        task_id="2026-0604-0001",
                        task_title="write draft",
                        elapsed_seconds=25 * 60,
                    ),
                    SummaryTaskEntry(
                        task_id="2026-0604-0002",
                        task_title="review notes",
                        elapsed_seconds=15 * 60,
                    ),
                ],
            )
        )

        self.assertIn("tasks_worked_on_today: 2", rendered)
        self.assertIn("tasks_completed_today: 1", rendered)
        self.assertIn("2026-0604-0001 write draft: 25m 0s", rendered)

    def test_format_backlog_renders_ordered_planned_tasks(self) -> None:
        rendered = format_backlog(
            [
                BacklogEntry(
                    position=1,
                    task_id="2026-1004-0001",
                    task_title="review failing tests",
                    estimate_minutes=15,
                    priority="high",
                    source_parent_title="Ship pomo update",
                    state="planned",
                ),
                BacklogEntry(
                    position=2,
                    task_id="2026-1004-0002",
                    task_title="write release note",
                    estimate_minutes=10,
                    priority="medium",
                    source_parent_title="Ship pomo update",
                    state="planned",
                ),
            ]
        )

        self.assertIn("1. [high] review failing tests (15m) task_id=2026-1004-0001 state=planned parent=Ship pomo update", rendered)
        self.assertIn("2. [medium] write release note (10m) task_id=2026-1004-0002 state=planned parent=Ship pomo update", rendered)


class CliFlowTests(unittest.TestCase):
    def _base_env(self, temp_home: str) -> dict[str, str]:
        return {**os.environ, "HOME": temp_home}

    def _seed_store(self, temp_home: str) -> PomoService:
        db_path = Path(temp_home) / ".pomo-cli" / "pomo.db"
        store = PomoStore(db_path)
        store.initialize()
        return PomoService(store)

    def test_start_runs_countdown_and_closes_the_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            stdout = io.StringIO()
            stderr = io.StringIO()
            ticks = iter(
                [
                    datetime(2026, 4, 2, 14, 0, 0),
                    datetime(2026, 4, 2, 14, 0, 30),
                    datetime(2026, 4, 2, 14, 1, 0),
                ]
            )

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["start", "--task", "write 500-word essay", "--minutes", "1"],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: next(ticks),
                    sleep_fn=lambda _seconds: None,
                )

            service = self._seed_store(temp_home)
            final_status = service.get_status(now=datetime(2026, 4, 2, 14, 1, 0))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(final_status.state, "session_closed")
        self.assertEqual(final_status.total_elapsed_seconds, 60)
        self.assertIn("state: running", stdout.getvalue())
        self.assertIn("task_title: write 500-word essay", stdout.getvalue())
        self.assertIn("00:00", stdout.getvalue())

    def test_start_interrupt_leaves_the_session_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            stdout = io.StringIO()
            stderr = io.StringIO()
            ticks = iter(
                [
                    datetime(2026, 4, 2, 14, 0, 0),
                    datetime(2026, 4, 2, 14, 0, 5),
                ]
            )

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["start", "--task", "interrupt me", "--minutes", "1"],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: next(ticks),
                    sleep_fn=lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
                )

            service = self._seed_store(temp_home)
            final_status = service.get_status(now=datetime(2026, 4, 2, 14, 0, 5))

        self.assertEqual(exit_code, 130)
        self.assertEqual(final_status.state, "running")
        self.assertEqual(final_status.total_elapsed_seconds, 0)
        self.assertIn("state: running", stdout.getvalue())

    def test_watch_interrupt_leaves_the_session_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            status = service.start_new_task(
                task_title="watch me",
                planned_minutes=25,
                now=datetime(2026, 4, 6, 14, 0, 0),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            ticks = iter(
                [
                    datetime(2026, 4, 6, 14, 0, 0),
                    datetime(2026, 4, 6, 14, 0, 5),
                ]
            )

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["watch"],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: next(ticks),
                    sleep_fn=lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
                )

            refreshed = service.get_task_status(
                status.task_id,
                now=datetime(2026, 4, 6, 14, 0, 5),
            )

        self.assertEqual(exit_code, 130)
        self.assertEqual(refreshed.state, "running")

    def test_continue_without_task_id_starts_a_new_session_for_the_latest_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            first = service.start_new_task(
                task_title="write draft",
                planned_minutes=25,
                now=datetime(2026, 4, 6, 9, 0, 0),
            )
            service.close_active_session(now=datetime(2026, 4, 6, 9, 25, 0))

            stdout = io.StringIO()
            stderr = io.StringIO()
            ticks = iter(
                [
                    datetime(2026, 4, 6, 10, 0, 0),
                    datetime(2026, 4, 6, 10, 0, 5),
                ]
            )

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["continue", "--minutes", "10"],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: next(ticks),
                    sleep_fn=lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
                )

            refreshed = service.get_status(now=datetime(2026, 4, 6, 10, 0, 5))

        self.assertEqual(exit_code, 130)
        self.assertEqual(refreshed.task_id, first.task_id)
        self.assertEqual(refreshed.state, "running")
        self.assertIn(f"task_id: {first.task_id}", stdout.getvalue())

    def test_watch_returns_error_when_no_session_is_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(["watch"], stdout=stdout, stderr=stderr)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("no active session", stderr.getvalue())

    def test_backlog_prints_planned_tasks_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            service.plan_tasks(
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

            result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "backlog"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("1. [high] review failing tests (15m)", result.stdout)
        self.assertIn("2. [medium] write release note (10m)", result.stdout)
        self.assertIn("parent=Ship pomo update", result.stdout)
        self.assertIn("state=planned", result.stdout)

    def test_plan_reads_json_file_and_prints_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            stdout = io.StringIO()
            stderr = io.StringIO()
            plan_path = Path(temp_home) / "plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "parent_title": "Ship pomo update",
                        "subtasks": [
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
                    }
                )
            )

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["plan", "--file", str(plan_path)],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: datetime(2026, 4, 10, 9, 0, 0),
                )

            service = self._seed_store(temp_home)
            backlog = service.backlog_for_date("2026-04-10")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(backlog), 2)
        self.assertIn("1. [high] review failing tests (15m)", stdout.getvalue())
        self.assertIn("2. [medium] write release note (10m)", stdout.getvalue())

    def test_plan_rejects_invalid_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            stdout = io.StringIO()
            stderr = io.StringIO()
            plan_path = Path(temp_home) / "plan.json"
            plan_path.write_text("{not-json")

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["plan", "--file", str(plan_path)],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: datetime(2026, 4, 10, 9, 0, 0),
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("invalid plan file", stderr.getvalue().lower())

    def test_run_with_task_id_starts_a_planned_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            planned = service.plan_tasks(
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
            stdout = io.StringIO()
            stderr = io.StringIO()
            ticks = iter(
                [
                    datetime(2026, 4, 10, 9, 30, 0),
                    datetime(2026, 4, 10, 9, 30, 5),
                ]
            )

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["run", "--task-id", planned.task_id],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: next(ticks),
                    sleep_fn=lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
                )

            refreshed = service.get_status(now=datetime(2026, 4, 10, 9, 30, 5))

        self.assertEqual(exit_code, 130)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(refreshed.task_id, planned.task_id)
        self.assertEqual(refreshed.state, "running")
        self.assertIn(f"task_id: {planned.task_id}", stdout.getvalue())
        self.assertIn("planned_minutes: 15", stdout.getvalue())

    def test_run_with_position_resolves_same_task_shown_in_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            service.plan_tasks(
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
            stdout = io.StringIO()
            stderr = io.StringIO()
            ticks = iter(
                [
                    datetime(2026, 4, 10, 9, 30, 0),
                    datetime(2026, 4, 10, 9, 30, 5),
                ]
            )

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["run", "--position", "2"],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: next(ticks),
                    sleep_fn=lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
                )

            refreshed = service.get_status(now=datetime(2026, 4, 10, 9, 30, 5))

        self.assertEqual(exit_code, 130)
        self.assertEqual(refreshed.task_title, "write release note")
        self.assertIn("task_title: write release note", stdout.getvalue())
        self.assertIn("planned_minutes: 10", stdout.getvalue())

    def test_run_rejects_non_planned_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            task = service.start_new_task(
                task_title="write 500-word essay",
                planned_minutes=25,
                now=datetime(2026, 4, 10, 9, 0, 0),
            )
            service.close_active_session(now=datetime(2026, 4, 10, 9, 25, 0))
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch.dict(os.environ, {"HOME": temp_home}, clear=False):
                exit_code = main(
                    ["run", "--task-id", task.task_id],
                    stdout=stdout,
                    stderr=stderr,
                    now_fn=lambda: datetime(2026, 4, 10, 9, 30, 0),
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("run only works for planned backlog tasks", stderr.getvalue())

    def test_status_returns_error_when_no_task_is_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "status"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("no tracked task", result.stderr.lower())

    def test_status_prints_active_task_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            status = service.start_new_task(
                task_title="write 500-word essay",
                planned_minutes=25,
                now=datetime.now().replace(microsecond=0),
            )

            result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "status"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("state: running", result.stdout)
        self.assertIn(f"task_id: {status.task_id}", result.stdout)
        self.assertIn("task_title: write 500-word essay", result.stdout)
        self.assertIn("planned_minutes: 25", result.stdout)
        self.assertIn("scheduled_end_at:", result.stdout)
        self.assertNotIn("\nends_at:", "\n" + result.stdout)
        self.assertNotIn("remaining:", result.stdout)

    def test_status_falls_back_to_one_line_planned_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            planned = service.plan_tasks(
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

            result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "status"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn(f"task_id={planned.task_id}", result.stdout)
        self.assertIn("state=planned", result.stdout)
        self.assertIn("estimate=15m", result.stdout)
        self.assertIn("priority=high", result.stdout)
        self.assertNotIn("scheduled_end_at:", result.stdout)

    def test_complete_latest_ignores_planned_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            started_at = datetime.now().replace(microsecond=0) - timedelta(minutes=5)
            worked = service.start_new_task(
                task_title="write 500-word essay",
                planned_minutes=25,
                now=started_at,
            )
            service.close_active_session(now=started_at + timedelta(minutes=5))
            service.plan_tasks(
                parent_title="Ship pomo update",
                subtasks=[
                    {
                        "task_title": "review failing tests",
                        "estimate_minutes": 15,
                        "priority": "high",
                    }
                ],
                now=started_at + timedelta(minutes=10),
            )

            complete_result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "complete", "--latest"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )

        self.assertEqual(complete_result.returncode, 0)
        self.assertIn(f"task_id: {worked.task_id}", complete_result.stdout)
        self.assertNotIn("review failing tests", complete_result.stdout)

    def test_complete_with_task_id_allows_planned_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            planned = service.plan_tasks(
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

            complete_result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "complete", "--task-id", planned.task_id],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )

        self.assertEqual(complete_result.returncode, 0)
        self.assertIn(f"task_id={planned.task_id}", complete_result.stdout)
        self.assertIn("state=completed", complete_result.stdout)
        self.assertIn("total_time_spent=0s", complete_result.stdout)
        self.assertNotIn("scheduled_end_at:", complete_result.stdout)

    def test_complete_latest_and_summary_report_completed_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            started_at = datetime.now().replace(microsecond=0) - timedelta(minutes=5)
            status = service.start_new_task(
                task_title="write 500-word essay",
                planned_minutes=25,
                now=started_at,
            )
            service.close_active_session(now=started_at + timedelta(minutes=5))

            complete_result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "complete", "--latest"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )
            summary_result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "summary"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )

        self.assertEqual(complete_result.returncode, 0)
        self.assertIn("state: completed", complete_result.stdout)
        self.assertIn(f"task_id: {status.task_id}", complete_result.stdout)
        self.assertIn("task_title: write 500-word essay", complete_result.stdout)
        self.assertIn("scheduled_end_at:", complete_result.stdout)
        self.assertIn("completed_at:", complete_result.stdout)
        self.assertIn("total_time_spent: 5m 0s", complete_result.stdout)
        self.assertEqual(summary_result.returncode, 0)
        self.assertIn("tasks_worked_on_today: 1", summary_result.stdout)
        self.assertIn("tasks_completed_today: 1", summary_result.stdout)
        self.assertIn("total_time_spent_today: 5m 0s", summary_result.stdout)
        self.assertIn(f"{status.task_id} write 500-word essay: 5m 0s", summary_result.stdout)

    def test_summary_reports_worked_today_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            service = self._seed_store(temp_home)
            now = datetime.now().replace(microsecond=0)
            status = service.start_new_task(
                task_title="write 500-word essay",
                planned_minutes=25,
                now=now,
            )
            service.close_active_session(now=now + timedelta(minutes=5))

            summary_result = subprocess.run(
                [sys.executable, "-m", "pomo_cli", "summary"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=self._base_env(temp_home),
            )

        self.assertEqual(summary_result.returncode, 0)
        self.assertIn("tasks_worked_on_today: 1", summary_result.stdout)
        self.assertIn("tasks_completed_today: 0", summary_result.stdout)
        self.assertIn(f"{status.task_id} write 500-word essay: 5m 0s", summary_result.stdout)


if __name__ == "__main__":
    unittest.main()
