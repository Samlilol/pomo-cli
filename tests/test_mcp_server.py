import importlib.util
import io
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from pomo_cli.service import PomoService
from pomo_cli.store import PomoStore


HAS_MCP = importlib.util.find_spec("mcp") is not None


class McpServerTests(unittest.TestCase):
    def _make_service(self) -> PomoService:
        import tempfile

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        db_path = Path(self.temp_dir.name) / "pomo.db"
        store = PomoStore(db_path)
        store.initialize()
        return PomoService(store)

    def _create_server(
        self,
        service: PomoService,
        now_fn=lambda: datetime(2026, 4, 10, 9, 0, 0),
    ):
        if not HAS_MCP:
            self.skipTest("mcp package is not installed")
        from pomo_cli import mcp_server

        return mcp_server.create_server(service=service, now_fn=now_fn)

    def test_main_reports_missing_mcp_dependency_without_traceback(self) -> None:
        from pomo_cli import mcp_server

        stderr = io.StringIO()
        with patch.object(mcp_server, "_load_fastmcp", side_effect=ImportError("missing mcp")):
            exit_code = mcp_server.main(stderr=stderr)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr.getvalue().strip(), "Install pomo-cli[mcp] to use the MCP server.")

    def test_pyproject_declares_mcp_script_and_optional_dependency(self) -> None:
        pyproject_text = Path(__file__).resolve().parents[1].joinpath("pyproject.toml").read_text(
            encoding="utf-8"
        )

        self.assertIn('pomo-mcp = "pomo_cli.mcp_server:main"', pyproject_text)
        self.assertIn("[project.optional-dependencies]", pyproject_text)
        self.assertIn('mcp = ["mcp>=1,<2"]', pyproject_text)

    def test_setup_py_is_removed(self) -> None:
        setup_path = Path(__file__).resolve().parents[1] / "setup.py"
        self.assertFalse(setup_path.exists())

    def test_gitignore_covers_build_outputs(self) -> None:
        gitignore_text = Path(__file__).resolve().parents[1].joinpath(".gitignore").read_text(
            encoding="utf-8"
        )

        self.assertIn("dist/", gitignore_text)
        self.assertIn("build/", gitignore_text)

    def test_claude_skill_does_not_hardcode_personal_repo_path(self) -> None:
        skill_text = (
            Path(__file__).resolve().parents[1]
            .joinpath(".claude", "skills", "pomo", "SKILL.md")
            .read_text(encoding="utf-8")
        )

        self.assertNotIn("~/Desktop/Study Repo/pomo-cli", skill_text)
        self.assertNotIn("Desktop/Study Repo", skill_text)

    def test_create_server_exposes_expected_tools(self) -> None:
        server = self._create_server(service=self._make_service())

        self.assertEqual(
            set(server._pomo_tools),
            {
                "start_task",
                "complete_task",
                "get_status",
                "get_summary",
                "get_backlog",
                "plan_tasks",
                "run_planned_task",
                "continue_task",
            },
        )

    def test_start_task_returns_json_serializable_payload(self) -> None:
        server = self._create_server(service=self._make_service())

        payload = server._pomo_tools["start_task"]("write docs", 25)

        self.assertEqual(payload["state"], "running")
        self.assertEqual(payload["task_title"], "write docs")
        self.assertEqual(payload["planned_minutes"], 25)
        self.assertEqual(payload["starts_at"], "2026-04-10T09:00:00")

    def test_get_summary_uses_now_fn_when_date_is_omitted(self) -> None:
        service = self._make_service()
        service.start_new_task(
            task_title="write docs",
            planned_minutes=25,
            now=datetime(2026, 4, 10, 8, 0, 0),
        )
        service.close_active_session(now=datetime(2026, 4, 10, 8, 5, 0))
        service.complete_task(
            task_ref=None,
            use_latest=True,
            now=datetime(2026, 4, 10, 8, 5, 0),
        )

        server = self._create_server(
            service=service,
            now_fn=lambda: datetime(2026, 4, 10, 9, 0, 0),
        )

        payload = server._pomo_tools["get_summary"]()

        self.assertEqual(payload["tasks_worked_on_today"], 1)
        self.assertEqual(payload["tasks_completed_today"], 1)
        self.assertEqual(payload["total_time_spent_today"], 300)

    def test_get_backlog_uses_explicit_date_when_provided(self) -> None:
        service = self._make_service()
        service.plan_tasks(
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

        server = self._create_server(
            service=service,
            now_fn=lambda: datetime(2026, 4, 11, 9, 0, 0),
        )

        payload = server._pomo_tools["get_backlog"]("2026-04-10")

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["task_title"], "review failing tests")

    def test_get_summary_rejects_invalid_date_format(self) -> None:
        server = self._create_server(service=self._make_service())

        payload = server._pomo_tools["get_summary"]("04/10/2026")

        self.assertEqual(payload, {"error": "date must use YYYY-MM-DD"})

    def test_plan_tasks_invalid_priority_returns_error_payload(self) -> None:
        server = self._create_server(service=self._make_service())

        payload = server._pomo_tools["plan_tasks"](
            "Ship pomo update",
            [
                {
                    "task_title": "review failing tests",
                    "estimate_minutes": 15,
                    "priority": "urgent",
                }
            ],
        )

        self.assertEqual(payload, {"error": "priority must be one of: high, medium, low"})

    def test_continue_task_without_task_id_uses_latest_worked_task(self) -> None:
        service = self._make_service()
        first = service.start_new_task(
            task_title="write docs",
            planned_minutes=25,
            now=datetime(2026, 4, 10, 8, 0, 0),
        )
        service.close_active_session(now=datetime(2026, 4, 10, 8, 5, 0))

        server = self._create_server(service=service)

        payload = server._pomo_tools["continue_task"](None, 10)

        self.assertEqual(payload["task_id"], first.task_id)
        self.assertEqual(payload["planned_minutes"], 10)

    def test_run_planned_task_supports_task_id_and_position(self) -> None:
        service = self._make_service()
        planned = service.plan_tasks(
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
        server = self._create_server(
            service=service,
            now_fn=lambda: datetime(2026, 4, 10, 9, 30, 0),
        )

        by_task_id = server._pomo_tools["run_planned_task"](planned[0].task_id, None, None)
        service.close_active_session(now=datetime(2026, 4, 10, 9, 31, 0))
        by_position = server._pomo_tools["run_planned_task"](None, 2, 20)

        self.assertEqual(by_task_id["task_title"], "review failing tests")
        self.assertEqual(by_position["task_title"], "write release note")
        self.assertEqual(by_position["planned_minutes"], 20)

    def test_double_start_returns_consistent_active_session_error(self) -> None:
        server = self._create_server(service=self._make_service())

        first = server._pomo_tools["start_task"]("write docs", 25)
        second = server._pomo_tools["start_task"]("review tests", 25)

        self.assertEqual(first["state"], "running")
        self.assertEqual(second, {"error": "an active session is already running"})

    def test_complete_task_requires_exactly_one_selector(self) -> None:
        server = self._create_server(service=self._make_service())

        missing = server._pomo_tools["complete_task"]()
        conflicting = server._pomo_tools["complete_task"]("2026-0410-0001", True)

        self.assertEqual(missing, {"error": "provide task_id or use_latest=true"})
        self.assertEqual(conflicting, {"error": "task_id and use_latest cannot be combined"})

    def test_integrity_error_is_normalized_to_active_session_error(self) -> None:
        service = self._make_service()
        server = self._create_server(service=service)

        with patch.object(service, "start_new_task", side_effect=sqlite3.IntegrityError("UNIQUE constraint failed: index 'sessions_single_active'")):
            payload = server._pomo_tools["start_task"]("write docs", 25)

        self.assertEqual(payload, {"error": "an active session is already running"})


if __name__ == "__main__":
    unittest.main()
