import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from pomo_cli.service import PomoService
from pomo_cli.store import PomoStore
from pomo_cli.timer import run_countdown


class TimerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pomo.db"
        self.store = PomoStore(self.db_path)
        self.store.initialize()
        self.service = PomoService(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_timer_expiry_closes_session(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=1,
            now=datetime(2026, 4, 2, 14, 0, 0),
        )
        output = io.StringIO()
        ticks = iter(
            [
                datetime(2026, 4, 2, 14, 0, 0),
                datetime(2026, 4, 2, 14, 0, 30),
                datetime(2026, 4, 2, 14, 1, 0),
            ]
        )

        run_countdown(
            service=self.service,
            task_id=status.task_id,
            stream=output,
            now_fn=lambda: next(ticks),
            sleep_fn=lambda _seconds: None,
        )

        final_status = self.service.get_task_status(
            status.task_id,
            now=datetime(2026, 4, 2, 14, 1, 0),
        )
        self.assertEqual(final_status.state, "session_closed")
        self.assertEqual(final_status.total_elapsed_seconds, 60)
        self.assertIn("00:00", output.getvalue())

    def test_external_completion_stops_countdown_without_double_counting(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=5,
            now=datetime(2026, 4, 2, 14, 0, 0),
        )
        output = io.StringIO()
        ticks = [
            datetime(2026, 4, 2, 14, 0, 0),
            datetime(2026, 4, 2, 14, 1, 0),
        ]

        def now_fn() -> datetime:
            current = ticks.pop(0)
            if current == datetime(2026, 4, 2, 14, 1, 0):
                self.service.complete_task(
                    task_ref=status.task_id,
                    use_latest=False,
                    now=current,
                )
            return current

        run_countdown(
            service=self.service,
            task_id=status.task_id,
            stream=output,
            now_fn=now_fn,
            sleep_fn=lambda _seconds: None,
        )

        final_status = self.service.get_task_status(
            status.task_id,
            now=datetime(2026, 4, 2, 14, 1, 0),
        )
        self.assertEqual(final_status.state, "completed")
        self.assertEqual(final_status.total_elapsed_seconds, 60)
        self.assertIn("Task completed.", output.getvalue())

    def test_session_closed_state_exits_countdown_cleanly(self) -> None:
        status = self.service.start_new_task(
            task_title="write 500-word essay",
            planned_minutes=5,
            now=datetime(2026, 4, 2, 14, 0, 0),
        )
        output = io.StringIO()
        ticks = [
            datetime(2026, 4, 2, 14, 0, 0),
            datetime(2026, 4, 2, 14, 1, 0),
        ]

        def now_fn() -> datetime:
            current = ticks.pop(0)
            if current == datetime(2026, 4, 2, 14, 1, 0):
                self.service.close_active_session(now=current)
            return current

        run_countdown(
            service=self.service,
            task_id=status.task_id,
            stream=output,
            now_fn=now_fn,
            sleep_fn=lambda _seconds: None,
        )

        final_status = self.service.get_task_status(
            status.task_id,
            now=datetime(2026, 4, 2, 14, 1, 0),
        )
        self.assertEqual(final_status.state, "session_closed")
        self.assertEqual(final_status.total_elapsed_seconds, 60)
        self.assertIn("00:00", output.getvalue())


if __name__ == "__main__":
    unittest.main()
