from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import textwrap
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "codex_runner_rate_limit_test_module",
    ROOT / "deploy/hermes-coders/codex_runner.py",
)
assert SPEC and SPEC.loader
codex_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = codex_runner
SPEC.loader.exec_module(codex_runner)


_FAKE_CODEX = r"""#!/usr/bin/env python3
import json
import os
import sys

mode = os.environ.get("FAKE_CODEX_MODE", "success")
account = {
    "id": 2,
    "result": {
        "account": {
            "type": "chatgpt",
            "planType": "plus",
        }
    },
}
weekly = {
    "id": 3,
    "result": {
        "rateLimits": {
            "primary": {
                "usedPercent": 31,
                "windowDurationMins": 10080,
                "resetsAt": 1800000000,
            },
            "secondary": None,
            "rateLimitReachedType": None,
        }
    },
}
failure = {
    "id": 3,
    "error": {
        "code": -32001,
        "message": "backend unavailable Authorization: Bearer abcdefghijklmnop",
    },
}

for raw in sys.stdin.buffer:
    request = json.loads(raw)
    request_id = request.get("id")
    if request_id == 1:
        os.write(
            sys.stdout.fileno(),
            (json.dumps({"id": 1, "result": {}}) + "\n").encode(),
        )
    elif request_id == 3:
        second = failure if mode == "error" else weekly
        payload = json.dumps(account) + "\n" + json.dumps(second) + "\n"
        os.write(sys.stdout.fileno(), payload.encode())
"""


class CodexRateLimitProbeTests(unittest.TestCase):
    def _fake_codex(self, root: Path) -> Path:
        executable = root / "codex"
        executable.write_text(textwrap.dedent(_FAKE_CODEX), encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def test_reads_two_responses_written_in_one_stdout_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            (home / "auth.json").write_text("{}", encoding="utf-8")
            result = codex_runner.read_codex_subscription_rate_limits(
                str(self._fake_codex(root)),
                home,
                timeout_seconds=2,
            )
        self.assertEqual("plus", result["plan_type"])
        self.assertIsNone(result["primary"])
        self.assertEqual(10080, result["secondary"]["window_duration_mins"])
        self.assertEqual(31.0, result["secondary"]["used_percent"])

    def test_classifies_windows_by_duration_instead_of_provider_slot(self) -> None:
        result = codex_runner.normalize_codex_subscription_rate_limits(
            {"account": {"type": "chatgpt", "planType": "plus"}},
            {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 40,
                        "windowDurationMins": 10080,
                    },
                    "secondary": {
                        "usedPercent": 20,
                        "windowDurationMins": 300,
                    },
                }
            },
        )
        self.assertEqual(300, result["primary"]["window_duration_mins"])
        self.assertEqual(10080, result["secondary"]["window_duration_mins"])

    def test_surfaces_sanitized_json_rpc_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            (home / "auth.json").write_text("{}", encoding="utf-8")
            with patch.dict(os.environ, {"FAKE_CODEX_MODE": "error"}):
                with self.assertRaisesRegex(RuntimeError, "backend unavailable") as raised:
                    codex_runner.read_codex_subscription_rate_limits(
                        str(self._fake_codex(root)),
                        home,
                        timeout_seconds=2,
                    )
        self.assertNotIn("abcdefghijklmnop", str(raised.exception))
        self.assertIn("[REDACTED]", str(raised.exception))

    def test_manager_maps_probe_failure_to_bad_gateway(self) -> None:
        manager = codex_runner.CodexManager.__new__(codex_runner.CodexManager)
        manager.codex_bin = "codex"
        manager.codex_home = Path("/tmp/codex-test")
        with patch.object(
            codex_runner,
            "read_codex_subscription_rate_limits",
            side_effect=RuntimeError("probe failed"),
        ):
            with self.assertRaises(codex_runner.RunnerError) as raised:
                manager.rate_limits()
        self.assertEqual(HTTPStatus.BAD_GATEWAY, raised.exception.status)
        self.assertEqual("probe failed", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
