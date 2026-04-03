from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable, TextIO

from pomo_cli.service import PomoService, StatusPayload, SummaryPayload
from pomo_cli.store import PomoStore
from pomo_cli.timer import run_countdown


def positive_int(value: str) -> int:
    minutes = int(value)
    if minutes <= 0:
        raise argparse.ArgumentTypeError("--minutes must be a positive integer")
    return minutes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pomo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start")
    start_group = start_parser.add_mutually_exclusive_group(required=True)
    start_group.add_argument("--task")
    start_group.add_argument("--task-id")
    start_group.add_argument("--latest", action="store_true")
    start_parser.add_argument("--minutes", type=positive_int, required=True)

    complete_parser = subparsers.add_parser("complete")
    complete_group = complete_parser.add_mutually_exclusive_group(required=True)
    complete_group.add_argument("--task-id")
    complete_group.add_argument("--latest", action="store_true")

    subparsers.add_parser("status")
    subparsers.add_parser("summary")
    return parser


def default_db_path() -> Path:
    return Path.home() / ".pomo-cli" / "pomo.db"


def build_service() -> PomoService:
    store = PomoStore(default_db_path())
    store.initialize()
    return PomoService(store)


def format_status(status: StatusPayload) -> str:
    return "\n".join(
        [
            f"state: {status.state}",
            f"task_id: {status.task_id}",
            f"task_title: {status.task_title}",
            f"planned_minutes: {status.planned_minutes}",
            f"remaining: {status.remaining_seconds}",
            f"starts_at: {status.starts_at.isoformat()}",
            f"ends_at: {status.ends_at.isoformat()}",
            f"total_time_spent: {status.total_elapsed_seconds}",
        ]
    )


def format_summary(summary: SummaryPayload) -> str:
    lines = [
        f"tasks_completed: {summary.tasks_completed}",
        f"total_time_spent_today: {summary.total_time_spent_today}",
    ]
    for task_title, elapsed_seconds in summary.time_spent_by_task.items():
        lines.append(f"{task_title}: {elapsed_seconds}")
    return "\n".join(lines)


def main(
    argv: list[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    now_fn: Callable[[], datetime] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = build_service()
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    now_fn = now_fn or datetime.now
    sleep_fn = sleep_fn or time.sleep

    if args.command == "start":
        current_time = now_fn()
        try:
            if args.task is not None:
                status = service.start_new_task(
                    task_title=args.task,
                    planned_minutes=args.minutes,
                    now=current_time,
                )
            else:
                status = service.start_existing_task(
                    task_ref=args.task_id,
                    use_latest=args.latest,
                    planned_minutes=args.minutes,
                    now=current_time,
                )
        except (RuntimeError, KeyError) as error:
            print(str(error), file=stderr)
            return 1
        print(format_status(status), file=stdout)
        try:
            run_countdown(
                service=service,
                task_id=status.task_id,
                stream=stdout,
                now_fn=now_fn,
                sleep_fn=sleep_fn,
            )
        except KeyboardInterrupt:
            active_session = service.store.get_active_session()
            if active_session is not None and active_session.task_id == status.task_id:
                service.close_active_session(now=now_fn())
            return 130
        return 0

    if args.command == "status":
        try:
            status = service.get_status()
        except RuntimeError as error:
            print(str(error), file=stderr)
            return 1
        print(format_status(status), file=stdout)
        return 0

    if args.command == "complete":
        try:
            status = service.complete_task(
                task_ref=args.task_id,
                use_latest=args.latest,
                now=now_fn(),
            )
        except (RuntimeError, KeyError) as error:
            print(str(error), file=stderr)
            return 1
        print(format_status(status), file=stdout)
        return 0

    if args.command == "summary":
        summary = service.summary_for_date(date.today().isoformat())
        print(format_summary(summary), file=stdout)
        return 0

    return 0
