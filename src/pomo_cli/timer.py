from __future__ import annotations

from datetime import datetime
from typing import Callable, TextIO

from pomo_cli.service import PomoService


def run_countdown(
    service: PomoService,
    task_id: str,
    stream: TextIO,
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
) -> None:
    while True:
        current_time = now_fn()
        status = service.get_task_status(task_id, now=current_time)

        if status.state == "completed":
            stream.write("Task completed.\n")
            stream.flush()
            return

        if status.state == "session_closed":
            stream.write("00:00\n")
            stream.flush()
            return

        if status.remaining_seconds <= 0:
            service.close_active_session(now=current_time)
            stream.write("00:00\n")
            stream.flush()
            return

        minutes, seconds = divmod(status.remaining_seconds, 60)
        stream.write(f"\r{minutes:02d}:{seconds:02d}")
        stream.flush()
        sleep_fn(1.0)
