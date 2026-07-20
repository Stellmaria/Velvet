from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.presentation.telegram.supervisor.contract import SupervisorCallback
from velvet_bot.supervisor_client import build_supervisor_client
from velvet_supervisor.git_ops import GitRepository
from velvet_supervisor.http_api import SupervisorHTTPServer


class SupervisorClientSettingsTests(unittest.TestCase):
    def test_build_client_is_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(build_supervisor_client())

    def test_build_client_reads_shared_token(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SUPERVISOR_ENABLED": "true",
                "SUPERVISOR_BASE_URL": "http://127.0.0.1:9876/",
                "SUPERVISOR_TOKEN": "a" * 32,
                "SUPERVISOR_CLIENT_TIMEOUT_SECONDS": "35",
            },
            clear=True,
        ):
            client = build_supervisor_client()
        self.assertIsNotNone(client)
        assert client is not None
        self.assertEqual(client.base_url, "http://127.0.0.1:9876")
        self.assertEqual(client.timeout_seconds, 35)

    def test_callback_data_fits_telegram_limit(self) -> None:
        packed = SupervisorCallback(
            action="codex.apply.ask",
            task_id="a" * 12,
        ).pack()
        self.assertLessEqual(len(packed.encode("utf-8")), 64)


class GitRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "tests@example.com"],
            cwd=self.path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Velvet Tests"],
            cwd=self.path,
            check=True,
        )
        (self.path / "README.md").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.path, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.path, check=True)
        self.repository = GitRepository(
            self.path,
            timeout_seconds=30,
            test_command=(sys.executable, "-c", "print('tests ok')"),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_commit_all_creates_commit(self) -> None:
        (self.path / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
        commit = self.repository.commit_all("feature", cwd=self.path)
        self.assertEqual(commit, self.repository.head_sha())
        self.assertFalse(self.repository.status_porcelain())

    def test_commit_all_rejects_env_secret(self) -> None:
        (self.path / ".env.production").write_text("TOKEN=secret\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "запрещённые файлы"):
            self.repository.commit_all("bad", cwd=self.path)
        staged = self.repository.git(
            "diff",
            "--cached",
            "--name-only",
            cwd=self.path,
        ).output
        self.assertEqual(staged.strip(), "")


class _FakeCodex:
    def list_tasks(self, *, limit: int = 20):
        return []

    def get_dict(self, task_id: str):
        return {"id": task_id, "status": "ready"}


class _FakeRuntime:
    def __init__(self, token: str) -> None:
        self.settings = SimpleNamespace(api_token=token)
        self.codex = _FakeCodex()

    def status(self):
        return {"bot": {"running": True}}

    def log_tail(self, lines: int):
        return ["line 1", "line 2"][-lines:]


class SupervisorHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = "t" * 32
        self.server = SupervisorHTTPServer(
            ("127.0.0.1", 0),
            _FakeRuntime(self.token),  # type: ignore[arg-type]
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _request(self, path: str, *, token: str | None):
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.base_url + path, headers=headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_health_does_not_require_token(self) -> None:
        status, payload = self._request("/health", token=None)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_status_requires_token(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self._request("/v1/status", token="wrong")
        self.assertEqual(context.exception.code, 401)

    def test_status_returns_runtime_snapshot(self) -> None:
        status, payload = self._request("/v1/status", token=self.token)
        self.assertEqual(status, 200)
        self.assertTrue(payload["status"]["bot"]["running"])


if __name__ == "__main__":
    unittest.main()
