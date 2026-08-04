from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = (
    ROOT
    / "deploy/hermes-operator/plugins/kael-coder-control/__init__.py"
)

SPEC = importlib.util.spec_from_file_location(
    "kael_coder_control_test_module",
    PLUGIN_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load {PLUGIN_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeContext:
    def __init__(self) -> None:
        self.tools = []
        self.hooks = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))


class KaelCoderControlTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.audit_path = Path(directory.name) / "audit.jsonl"
        environment = patch.dict(
            os.environ,
            {"KAEL_CODER_AUDIT_PATH": str(self.audit_path)},
            clear=False,
        )
        environment.start()
        self.addCleanup(environment.stop)

    def delegate_args(self, **changes):
        values = {
            "project": "velvet",
            "task_type": "read_only",
            "complexity": "small",
            "risk": "low",
            "mutation_policy": "read_only",
            "requested_tier": "small",
            "task": "Проверь состояние проекта без изменений.",
        }
        values.update(changes)
        return values

    def test_registers_typed_tool_in_telegram_toolset_and_both_hooks(self) -> None:
        context = FakeContext()
        MODULE.register(context)

        self.assertEqual(["coder_delegate"], [item["name"] for item in context.tools])
        self.assertEqual("hermes-telegram", MODULE.TELEGRAM_TOOLSET)
        self.assertEqual(MODULE.TELEGRAM_TOOLSET, context.tools[0]["toolset"])
        schema = context.tools[0]["schema"]["parameters"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            sorted(MODULE._REQUIRED_FIELDS),
            sorted(schema["required"]),
        )
        self.assertEqual(
            {"pre_tool_call", "post_tool_call"},
            {name for name, _callback in context.hooks},
        )

    def test_handler_uses_argv_without_shell_and_returns_metadata(self) -> None:
        response = {
            "task_id": "a" * 32,
            "run_id": "run_velvet",
            "status": "queued",
            "selected_primary_model": "gpt-5.6-luna",
            "actual_route": "codex_subscription",
            "attempted_routes": ["codex_subscription:gpt-5.6-luna"],
            "mutation_started": False,
        }
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(response),
            stderr="",
        )

        with patch.object(
            MODULE.subprocess,
            "run",
            return_value=completed,
        ) as run:
            result = json.loads(
                MODULE._handle_coder_delegate(self.delegate_args())
            )

        command = run.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(MODULE.CODERCTL_PATH, command[1])
        self.assertIn("submit", command)
        self.assertIn("--task-type", command)
        self.assertEqual("gpt-5.6-luna", result["selected_primary_model"])
        self.assertEqual("codex_subscription", result["actual_route"])
        self.assertEqual("small", result["requested_tier"])
        self.assertFalse(result["mutation_started"])
        self.assertFalse(result["production_privileges"])

    def test_invalid_project_is_rejected_before_subprocess(self) -> None:
        with patch.object(MODULE.subprocess, "run") as run:
            result = json.loads(
                MODULE._handle_coder_delegate(
                    self.delegate_args(project="other")
                )
            )

        self.assertFalse(result["ok"])
        self.assertIn("Invalid project", result["error"])
        run.assert_not_called()

    def test_unknown_field_is_rejected(self) -> None:
        with patch.object(MODULE.subprocess, "run") as run:
            result = json.loads(
                MODULE._handle_coder_delegate(
                    {
                        **self.delegate_args(),
                        "backend": "local",
                    }
                )
            )

        self.assertFalse(result["ok"])
        self.assertIn("Unknown fields", result["error"])
        run.assert_not_called()

    def test_router_failure_is_explicit_and_has_no_local_fallback(self) -> None:
        completed = SimpleNamespace(
            returncode=2,
            stdout="",
            stderr=json.dumps(
                {
                    "ok": False,
                    "error": "Coder router недоступен: URLError",
                }
            ),
        )
        with patch.object(
            MODULE.subprocess,
            "run",
            return_value=completed,
        ):
            result = json.loads(
                MODULE._handle_coder_delegate(self.delegate_args())
            )

        self.assertFalse(result["ok"])
        self.assertIn("router недоступен", result["error"])
        self.assertIsNone(result["actual_route"])
        self.assertEqual([], result["attempted_routes"])
        self.assertFalse(result["mutation_started"])
        self.assertFalse(result["production_privileges"])

    def test_terminal_allows_only_validated_controller_commands(self) -> None:
        allowed = (
            "python /opt/data/tools/monitorctl.py summary",
            "python /opt/data/tools/opsctl.py velvet status",
            "python /opt/data/tools/reconcilectl.py submit entities",
            "python /opt/data/tools/runctl.py status run_123",
            "python /opt/data/tools/coderctl.py health all",
            "python /opt/data/tools/coderctl.py status abc123",
            "python /opt/data/tools/coderctl.py pr velvet 593",
            "/opt/data/tools/monitorctl.py resources",
        )
        for command in allowed:
            with self.subTest(command=command):
                self.assertIsNone(
                    MODULE._on_pre_tool_call(
                        tool_name="terminal",
                        args={"command": command},
                    )
                )

    def test_terminal_blocks_shell_git_repo_and_submit_bypass(self) -> None:
        blocked = (
            "git status",
            "gh pr list",
            "cd /opt/data/workspace/Velvet",
            "python -c 'print(1)'",
            "cat /etc/os-release",
            "python /opt/data/tools/coderctl.py submit velvet --task x",
            "python /opt/data/tools/monitorctl.py summary; git status",
        )
        for command in blocked:
            with self.subTest(command=command):
                result = MODULE._on_pre_tool_call(
                    tool_name="terminal",
                    args={"command": command},
                )
                self.assertEqual("block", result["action"])

    def test_terminal_blocks_unknown_controller_actions_and_targets(self) -> None:
        blocked = (
            "python /opt/data/tools/monitorctl.py shell",
            "python /opt/data/tools/opsctl.py other status",
            "python /opt/data/tools/opsctl.py velvet shell",
            "python /opt/data/tools/reconcilectl.py submit unknown",
            "python /opt/data/tools/runctl.py submit run_123",
            "python /opt/data/tools/coderctl.py submit velvet",
        )
        for command in blocked:
            with self.subTest(command=command):
                result = MODULE._on_pre_tool_call(
                    tool_name="terminal",
                    args={"command": command},
                )
                self.assertEqual("block", result["action"])

    def test_local_search_and_code_execution_are_blocked(self) -> None:
        for tool_name in ("search_files", "execute_code", "python_repl"):
            with self.subTest(tool_name=tool_name):
                result = MODULE._on_pre_tool_call(
                    tool_name=tool_name,
                    args={},
                )
                self.assertEqual("block", result["action"])

    def test_workspace_file_access_is_blocked(self) -> None:
        blocked = (
            "/opt/data/workspace/Velvet/README.md",
            "workspace/Velvet/README.md",
            "/srv/velvet/README.md",
            "/srv/romatic-club-max/README.md",
        )
        for path in blocked:
            with self.subTest(path=path):
                result = MODULE._on_pre_tool_call(
                    tool_name="read_file",
                    args={"path": path},
                )
                self.assertEqual("block", result["action"])

    def test_control_plane_files_are_immutable_to_model_tools(self) -> None:
        blocked = (
            "/opt/data/config.yaml",
            "/opt/data/.hermes-ops-client-token",
            "/opt/data/tools/coderctl.py",
            "/opt/data/plugins/kael-coder-control/__init__.py",
            "/opt/data/orchestration/tasks.json",
            "/opt/data/audit/kael-coder-control.jsonl",
            "/opt/data/provider-secret.txt",
        )
        for path in blocked:
            for tool_name in ("read_file", "write_file", "patch"):
                with self.subTest(path=path, tool_name=tool_name):
                    result = MODULE._on_pre_tool_call(
                        tool_name=tool_name,
                        args={"path": path, "content": "tampered"},
                    )
                    self.assertEqual("block", result["action"])

        self.assertIsNone(
            MODULE._on_pre_tool_call(
                tool_name="read_file",
                args={"path": "/opt/data/AGENTS.md"},
            )
        )

    def test_non_coder_delegation_is_preserved(self) -> None:
        self.assertIsNone(
            MODULE._on_pre_tool_call(
                tool_name="delegate_task",
                args={"agent": "queen", "task": "Проверь документ"},
            )
        )

    def test_direct_github_tool_is_blocked(self) -> None:
        result = MODULE._on_pre_tool_call(
            tool_name="github_create_pull_request",
            args={"repository": "Stellmaria/Velvet"},
        )
        self.assertEqual("block", result["action"])

    def test_audit_does_not_store_task_text(self) -> None:
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "task_id": "b" * 32,
                    "run_id": "run_audit",
                    "status": "queued",
                    "attempted_routes": [],
                    "mutation_started": False,
                }
            ),
            stderr="",
        )
        task = "Секретный текст задачи, который не должен попасть в audit."
        with patch.object(
            MODULE.subprocess,
            "run",
            return_value=completed,
        ):
            MODULE._handle_coder_delegate(self.delegate_args(task=task))

        audit = self.audit_path.read_text(encoding="utf-8")
        self.assertNotIn(task, audit)
        self.assertIn("task_sha256", audit)
        self.assertIn("delegate_invocation", audit)
        self.assertIn("router_submit", audit)
        self.assertIn("router_result", audit)

    def test_audit_refuses_symlink_target(self) -> None:
        target = self.audit_path.parent / "target.jsonl"
        target.write_text("original\n", encoding="utf-8")
        symlink = self.audit_path.parent / "audit-link.jsonl"
        symlink.symlink_to(target)

        with patch.dict(
            os.environ,
            {"KAEL_CODER_AUDIT_PATH": str(symlink)},
            clear=False,
        ):
            MODULE._audit("must_not_follow")

        self.assertEqual("original\n", target.read_text(encoding="utf-8"))

    def test_terminal_failure_is_audited(self) -> None:
        MODULE._on_post_tool_call(
            tool_name="terminal",
            status="blocked",
            error_type="plugin_block",
            error_message="denied",
            task_id="task_1",
        )
        audit = self.audit_path.read_text(encoding="utf-8")
        self.assertIn("terminal_failure", audit)
        self.assertIn("plugin_block", audit)


if __name__ == "__main__":
    unittest.main()
