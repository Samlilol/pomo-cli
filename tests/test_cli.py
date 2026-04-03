import io
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from pomo_cli.cli import build_parser, main
from pomo_cli.service import PomoService
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
        self.assertIn("complete", result.stdout)
        self.assertIn("status", result.stdout)
        self.assertIn("summary", result.stdout)

    def test_status_parses(self) -> None:
        args = build_parser().parse_args(["status"])

        self.assertEqual(args.command, "status")

    def test_summary_parses(self) -> None:
        args = build_parser().parse_args(["summary"])

        self.assertEqual(args.command, "summary")

    def test_start_with_task_parses(self) -> None:
        args = build_parser().parse_args(["start", "--task", "Write tests", "--minutes", "25"])

        self.assertEqual(args.command, "start")
        self.assertEqual(args.task, "Write tests")
        self.assertIsNone(args.task_id)
        self.assertFalse(args.latest)
        self.assertEqual(args.minutes, 25)

    def test_start_with_task_id_parses(self) -> None:
        args = build_parser().parse_args(["start", "--task-id", "123", "--minutes", "25"])

        self.assertEqual(args.command, "start")
        self.assertIsNone(args.task)
        self.assertEqual(args.task_id, "123")
        self.assertFalse(args.latest)
        self.assertEqual(args.minutes, 25)

    def test_start_latest_parses(self) -> None:
        args = build_parser().parse_args(["start", "--latest", "--minutes", "25"])

        self.assertEqual(args.command, "start")
        self.assertIsNone(args.task)
        self.assertIsNone(args.task_id)
        self.assertTrue(args.latest)
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

    def test_start_rejects_zero_minutes(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start", "--task", "Write tests", "--minutes", "0"])

    def test_start_rejects_negative_minutes(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["start", "--task", "Write tests", "--minutes", "-5"])

    def test_complete_rejects_multiple_selectors(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["complete", "--task-id", "123", "--latest"])


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

    def test_start_interrupt_closes_the_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_home:
            stdout = io.StringIO()
            stderr = io.StringIO()
            ticks = iter(
                [
                    datetime(2026, 4, 2, 14, 0, 0),
                    datetime(2026, 4, 2, 14, 0, 5),
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
        self.assertEqual(final_status.state, "session_closed")
        self.assertEqual(final_status.total_elapsed_seconds, 5)
        self.assertIn("state: running", stdout.getvalue())

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
        self.assertEqual(summary_result.returncode, 0)
        self.assertIn("tasks_completed: 1", summary_result.stdout)
        self.assertIn("total_time_spent_today: 300", summary_result.stdout)
        self.assertIn("write 500-word essay: 300", summary_result.stdout)


if __name__ == "__main__":
    unittest.main()
