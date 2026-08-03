from __future__ import annotations

import json
import threading
import time
import unittest
from unittest.mock import patch

from velvet_supervisor.hermes_incident import (
    HermesIncident,
    HermesIncidentClient,
    redact_sensitive,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class HermesIncidentTests(unittest.TestCase):
    def _incident(self) -> HermesIncident:
        fake_bot_token = "1234567890:" + "abcdefghijklmnopqrstuvwxyzABCDE"
        return HermesIncident(
            service="velvet-bot",
            reason="Repeated crash",
            exit_code=1,
            restart_count=3,
            crash_loop_open=True,
            log_tail=(
                "Authorization: Bearer super-secret-token\n"
                "DATABASE_URL=postgresql://velvet:database-password@postgres:5432/velvet\n"
                f"BOT_TOKEN={fake_bot_token}\n"
                "RuntimeError: worker failed 123 times"
            ),
            git_head="abc123",
            branch="main",
        )

    def test_redacts_tokens_and_database_passwords(self) -> None:
        redacted = redact_sensitive(self._incident().log_tail)
        self.assertNotIn("super-secret-token", redacted)
        self.assertNotIn("database-password", redacted)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyzABCDE", redacted)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), 3)

    def test_submits_to_runs_api_and_returns_run_id(self) -> None:
        client = HermesIncidentClient(
            enabled=True,
            base_url="http://hermes:8642",
            api_key="12345678",
        )
        with patch(
            "velvet_supervisor.hermes_incident.urllib.request.urlopen",
            return_value=_FakeResponse({"run_id": "run_123", "status": "started"}),
        ) as urlopen:
            run_id = client.submit(self._incident())
        self.assertEqual(run_id, "run_123")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://hermes:8642/v1/runs")
        body = json.loads(request.data.decode("utf-8"))
        self.assertIn("input", body)
        self.assertIn("session_id", body)
        self.assertIn("coderctl.py submit velvet", body["input"])
        self.assertIn("--source incident", body["input"])
        self.assertIn("--task-type incident", body["input"])
        self.assertIn("--complexity complex", body["input"])
        self.assertIn("--risk high", body["input"])
        self.assertIn("--mutation-policy isolated_pr_only", body["input"])
        self.assertIn("--tier high_risk", body["input"])
        self.assertIn("requested_tier, actual_route", body["input"])
        self.assertNotIn("super-secret-token", body["input"])
        self.assertNotIn("database-password", body["input"])

    def test_async_run_waits_for_terminal_result_and_invokes_callback(self) -> None:
        responses = iter(
            (
                _FakeResponse({"run_id": "run_123", "status": "started"}),
                _FakeResponse(
                    {
                        "run_id": "run_123",
                        "status": "completed",
                        "output": "PR ready",
                    }
                ),
            )
        )
        callback_event = threading.Event()
        reports: list[dict[str, object]] = []
        client = HermesIncidentClient(
            enabled=True,
            base_url="http://hermes:8642",
            api_key="12345678",
            poll_interval_seconds=0.01,
            run_timeout_seconds=60,
            result_callback=lambda report: (reports.append(report), callback_event.set()),
        )
        with patch(
            "velvet_supervisor.hermes_incident.urllib.request.urlopen",
            side_effect=lambda *args, **kwargs: next(responses),
        ):
            self.assertTrue(client.submit_async(self._incident()))
            self.assertTrue(callback_event.wait(1))
        self.assertEqual("completed", reports[0]["status"])
        self.assertEqual("PR ready", reports[0]["output"])
        self.assertEqual("finished", client.status()["state"])

    def test_deduplicates_same_incident_during_cooldown(self) -> None:
        client = HermesIncidentClient(
            enabled=True,
            base_url="http://hermes:8642",
            api_key="12345678",
            cooldown_seconds=600,
        )
        client.submit = lambda incident: "run_test"  # type: ignore[method-assign]
        client.wait_for_run = lambda run_id: {  # type: ignore[method-assign]
            "run_id": run_id,
            "status": "completed",
            "output": "done",
        }
        self.assertTrue(client.submit_async(self._incident()))
        self.assertFalse(client.submit_async(self._incident()))
        time.sleep(0.02)
        self.assertIn(client.status()["state"], {"cooldown", "finished"})

    def test_disabled_client_does_not_start_thread(self) -> None:
        client = HermesIncidentClient(
            enabled=False,
            base_url="",
            api_key=None,
        )
        self.assertFalse(client.submit_async(self._incident()))
        self.assertEqual(client.status()["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
