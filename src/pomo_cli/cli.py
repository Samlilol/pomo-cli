from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable, TextIO

from pomo_cli.service import (
    PomoService,
    SessionlessStatusPayload,
    StatusPayload,
    SummaryPayload,
)
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
    start_parser.add_argument("--task", required=True)
    start_parser.add_argument("--minutes", type=positive_int, required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--file", required=True)

    run_parser = subparsers.add_parser("run")
    run_group = run_parser.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--task-id")
    run_group.add_argument("--position", type=positive_int)
    run_parser.add_argument("--minutes", type=positive_int)

    continue_parser = subparsers.add_parser("continue")
    continue_parser.add_argument("--task-id")
    continue_parser.add_argument("--minutes", type=positive_int, required=True)

    complete_parser = subparsers.add_parser("complete")
    complete_group = complete_parser.add_mutually_exclusive_group(required=True)
    complete_group.add_argument("--task-id")
    complete_group.add_argument("--latest", action="store_true")

    subparsers.add_parser("watch")
    subparsers.add_parser("status")
    subparsers.add_parser("summary")
    subparsers.add_parser("backlog")
    return parser


def default_db_path() -> Path:
    return Path.home() / ".pomo-cli" / "pomo.db"


def build_service() -> PomoService:
    store = PomoStore(default_db_path())
    store.initialize()
    return PomoService(store)


def load_plan_file(file_path: str) -> tuple[str, list[dict[str, object]]]:
    try:
        payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid plan file: {error}") from error

    if not isinstance(payload, dict):
        raise ValueError("invalid plan file: root payload must be an object")

    try:
        parent_title = str(payload["parent_title"]).strip()
        subtasks = payload["subtasks"]
    except KeyError as error:
        raise ValueError(f"invalid plan file: missing key {error.args[0]}") from error

    if not parent_title:
        raise ValueError("invalid plan file: parent_title is required")
    if not isinstance(subtasks, list):
        raise ValueError("invalid plan file: subtasks must be a list")

    return parent_title, subtasks


def format_duration(seconds: int) -> str:
    minutes, remaining_seconds = divmod(seconds, 60)
    if minutes == 0:
        return f"{remaining_seconds}s"
    return f"{minutes}m {remaining_seconds}s"


def format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def format_status(status: StatusPayload) -> str:
    lines = [
        f"state: {status.state}",
        f"task_id: {status.task_id}",
        f"task_title: {status.task_title}",
        f"planned_minutes: {status.planned_minutes}",
        f"starts_at: {format_timestamp(status.starts_at)}",
        f"scheduled_end_at: {format_timestamp(status.ends_at)}",
        f"total_time_spent: {format_duration(status.total_elapsed_seconds)}",
    ]
    if status.completed_at is not None:
        lines.append(f"completed_at: {format_timestamp(status.completed_at)}")
    return "\n".join(lines)


def format_sessionless_status(status: SessionlessStatusPayload) -> str:
    parts = [
        f"task_id={status.task_id}",
        f"task_title={status.task_title}",
        f"state={status.state}",
        f"total_time_spent={format_duration(status.total_elapsed_seconds)}",
    ]
    if status.estimate_minutes is not None:
        parts.append(f"estimate={status.estimate_minutes}m")
    if status.priority is not None:
        parts.append(f"priority={status.priority}")
    if status.source_parent_title:
        parts.append(f"parent={status.source_parent_title}")
    if status.completed_at is not None:
        parts.append(f"completed_at={format_timestamp(status.completed_at)}")
    return " ".join(parts)


def format_status_output(
    status: StatusPayload | SessionlessStatusPayload,
) -> str:
    if isinstance(status, StatusPayload):
        return format_status(status)
    return format_sessionless_status(status)


def format_summary(summary: SummaryPayload) -> str:
    lines = [
        f"tasks_worked_on_today: {summary.tasks_worked_on_today}",
        f"tasks_completed_today: {summary.tasks_completed_today}",
        f"total_time_spent_today: {format_duration(summary.total_time_spent_today)}",
    ]
    for entry in summary.task_entries:
        lines.append(
            f"{entry.task_id} {entry.task_title}: {format_duration(entry.elapsed_seconds)}"
        )
    return "\n".join(lines)


def format_backlog(entries: list) -> str:
    if not entries:
        return "no planned tasks for today"

    lines = []
    for entry in entries:
        parent_part = ""
        if entry.source_parent_title:
            parent_part = f" parent={entry.source_parent_title}"
        lines.append(
            f"{entry.position}. [{entry.priority}] {entry.task_title} ({entry.estimate_minutes}m) "
            f"task_id={entry.task_id} state={entry.state}{parent_part}"
        )
    return "\n".join(lines)


def run_watch_loop(
    service: PomoService,
    task_id: str,
    stdout: TextIO,
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
) -> int:
    try:
        run_countdown(
            service=service,
            task_id=task_id,
            stream=stdout,
            now_fn=now_fn,
            sleep_fn=sleep_fn,
        )
    except KeyboardInterrupt:
        stdout.write("\n")
        stdout.flush()
        return 130
    return 0


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
            status = service.start_new_task(
                task_title=args.task,
                planned_minutes=args.minutes,
                now=current_time,
            )
        except (RuntimeError, KeyError) as error:
            print(str(error), file=stderr)
            return 1
        print(format_status(status), file=stdout)
        return run_watch_loop(service, status.task_id, stdout, now_fn, sleep_fn)

    if args.command == "plan":
        try:
            parent_title, subtasks = load_plan_file(args.file)
            current_time = now_fn()
            service.plan_tasks(
                parent_title=parent_title,
                subtasks=subtasks,
                now=current_time,
            )
        except (RuntimeError, KeyError, ValueError) as error:
            print(str(error), file=stderr)
            return 1
        backlog = service.backlog_for_date(current_time.date().isoformat())
        print(format_backlog(backlog), file=stdout)
        return 0

    if args.command == "run":
        try:
            status = service.run_planned_task(
                task_ref=args.task_id,
                position=args.position,
                planned_minutes=args.minutes,
                now=now_fn(),
            )
        except (RuntimeError, KeyError) as error:
            print(str(error), file=stderr)
            return 1
        print(format_status(status), file=stdout)
        return run_watch_loop(service, status.task_id, stdout, now_fn, sleep_fn)

    if args.command == "continue":
        try:
            status = service.continue_task(
                task_ref=args.task_id,
                planned_minutes=args.minutes,
                now=now_fn(),
            )
        except (RuntimeError, KeyError) as error:
            print(str(error), file=stderr)
            return 1
        print(format_status(status), file=stdout)
        return run_watch_loop(service, status.task_id, stdout, now_fn, sleep_fn)

    if args.command == "watch":
        active_session = service.store.get_active_session()
        if active_session is None:
            print("no active session", file=stderr)
            return 1
        return run_watch_loop(
            service,
            active_session.task_id,
            stdout,
            now_fn,
            sleep_fn,
        )

    if args.command == "status":
        try:
            status = service.get_status()
        except RuntimeError as error:
            print(str(error), file=stderr)
            return 1
        print(format_status_output(status), file=stdout)
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
        print(format_status_output(status), file=stdout)
        return 0

    if args.command == "summary":
        summary = service.summary_for_date(date.today().isoformat())
        print(format_summary(summary), file=stdout)
        return 0

    if args.command == "backlog":
        backlog = service.backlog_for_date(date.today().isoformat())
        print(format_backlog(backlog), file=stdout)
        return 0

    return 0
