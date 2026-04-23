from __future__ import annotations

import dataclasses
import sys
from datetime import datetime
from typing import Any, Callable, Type

from pomo_cli.cli import build_service
from pomo_cli.service import PomoService


def _load_fastmcp() -> Type[Any]:
    from mcp.server.fastmcp import FastMCP

    return FastMCP


def _error_message(error: BaseException) -> str:
    if isinstance(error, KeyError) and error.args:
        return str(error.args[0])
    return str(error)


def _error_payload(error: BaseException) -> dict[str, str]:
    return {"error": _error_message(error)}


def _to_dict(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _to_dict(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _to_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dict(item) for item in value]
    return value


def _today(now_fn: Callable[[], datetime]) -> str:
    return now_fn().date().isoformat()


def _clean_task_id(task_id: str | None) -> str | None:
    if task_id is None:
        return None
    text = str(task_id).strip()
    if not text:
        raise ValueError("task_id is required")
    return text


def _clean_position(position: int | None) -> int | None:
    if position is None:
        return None
    return _require_positive_int(position, "position")


def _clean_planned_minutes(planned_minutes: int | None) -> int | None:
    if planned_minutes is None:
        return None
    return _require_positive_int(planned_minutes, "planned_minutes")


def _require_non_empty_text(value: object, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return parsed


def _resolve_day(day: str | None, now_fn: Callable[[], datetime]) -> str:
    if day is None:
        return _today(now_fn)
    try:
        return datetime.strptime(day, "%Y-%m-%d").date().isoformat()
    except ValueError as error:
        raise ValueError("date must use YYYY-MM-DD") from error


def _normalize_known_error(error: BaseException) -> dict[str, str]:
    if isinstance(error, (RuntimeError, KeyError, ValueError)):
        return _error_payload(error)
    raise error


def create_server(
    service: PomoService,
    now_fn: Callable[[], datetime] | None = None,
) -> Any:
    FastMCP = _load_fastmcp()
    now_fn = now_fn or datetime.now
    mcp = FastMCP("pomo", json_response=True)

    @mcp.tool()
    def start_task(
        task_title: str | None = None,
        planned_minutes: int | None = None,
        task_id: str | None = None,
        position: int | None = None,
    ) -> dict[str, Any]:
        try:
            selected = sum(
                selector is not None for selector in (task_title, task_id, position)
            )
            if selected != 1:
                raise ValueError("provide exactly one of task_title, task_id, or position")
            if task_title is not None:
                if planned_minutes is None:
                    raise ValueError("planned_minutes is required when task_title is provided")
                payload = service.start_new_task(
                    task_title=_require_non_empty_text(task_title, "task_title"),
                    planned_minutes=_require_positive_int(
                        planned_minutes,
                        "planned_minutes",
                    ),
                    now=now_fn(),
                )
            else:
                payload = service.run_planned_task(
                    task_ref=_clean_task_id(task_id),
                    position=_clean_position(position),
                    planned_minutes=_clean_planned_minutes(planned_minutes),
                    now=now_fn(),
                )
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    @mcp.tool()
    def complete_task(
        task_id: str | None = None,
        use_latest: bool = False,
    ) -> dict[str, Any]:
        try:
            if task_id is None and not use_latest:
                raise ValueError("provide task_id or use_latest=true")
            if task_id is not None and use_latest:
                raise ValueError("task_id and use_latest cannot be combined")
            payload = service.complete_task(
                task_ref=_clean_task_id(task_id),
                use_latest=use_latest,
                now=now_fn(),
            )
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    @mcp.tool()
    def get_status() -> dict[str, Any]:
        try:
            payload = service.get_status(now=now_fn())
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    @mcp.tool()
    def list_active_sessions() -> list[dict[str, Any]] | dict[str, str]:
        try:
            payload = service.get_all_active_statuses(now=now_fn())
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    @mcp.tool()
    def get_summary(date: str | None = None) -> dict[str, Any]:
        try:
            payload = service.summary_for_date(_resolve_day(date, now_fn))
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    @mcp.tool()
    def get_backlog(date: str | None = None) -> list[dict[str, Any]] | dict[str, str]:
        try:
            payload = service.backlog_for_date(_resolve_day(date, now_fn))
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    @mcp.tool()
    def plan_tasks(
        parent_title: str,
        subtasks: list[dict[str, object]],
    ) -> list[dict[str, Any]] | dict[str, str]:
        try:
            payload = service.plan_tasks(
                parent_title=_require_non_empty_text(parent_title, "parent_title"),
                subtasks=subtasks,
                now=now_fn(),
            )
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    @mcp.tool()
    def run_planned_task(
        task_id: str | None = None,
        position: int | None = None,
        planned_minutes: int | None = None,
    ) -> dict[str, Any]:
        try:
            if (task_id is None) == (position is None):
                raise ValueError("provide exactly one of task_id or position")
            payload = service.run_planned_task(
                task_ref=_clean_task_id(task_id),
                position=_clean_position(position),
                planned_minutes=_clean_planned_minutes(planned_minutes),
                now=now_fn(),
            )
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    @mcp.tool()
    def continue_task(
        task_id: str | None = None,
        planned_minutes: int = 25,
    ) -> dict[str, Any]:
        try:
            payload = service.continue_task(
                task_ref=_clean_task_id(task_id),
                planned_minutes=_require_positive_int(planned_minutes, "planned_minutes"),
                now=now_fn(),
            )
        except BaseException as error:
            return _normalize_known_error(error)
        return _to_dict(payload)

    mcp._pomo_tools = {
        "start_task": start_task,
        "complete_task": complete_task,
        "get_status": get_status,
        "list_active_sessions": list_active_sessions,
        "get_summary": get_summary,
        "get_backlog": get_backlog,
        "plan_tasks": plan_tasks,
        "run_planned_task": run_planned_task,
        "continue_task": continue_task,
    }
    return mcp


def main(stderr: Any = None) -> int:
    stderr = stderr or sys.stderr
    try:
        server = create_server(build_service())
    except ImportError:
        stderr.write("Install pomo-cli[mcp] to use the MCP server.\n")
        stderr.flush()
        return 1
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
