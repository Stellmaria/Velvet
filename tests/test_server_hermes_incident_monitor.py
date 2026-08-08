from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/hermes_incident_monitor.py"
spec = importlib.util.spec_from_file_location(
    "server_hermes_incident_monitor_test_module",
    MODULE_PATH,
)
assert spec and spec.loader
monitor_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = monitor_mod
spec.loader.exec_module(monitor_mod)


class ServerHermesIncidentMonitorTests(unittest.TestCase):
    def make_monitor(self, directory: str):
        environment = {
            "HERMES_INCIDENT_ENABLED": "false",
            "VELVET_APP_DIR": directory,
            "VELVET_DATA_DIR": directory,
            "VELVET_ENV_FILE": ".env.server",
            "VELVET_COMPOSE_FILE": "docker-compose.server.yml",
            "ALLOWED_USER_IDS": "12345,67890",
        }
        with patch.dict(os.environ, environment, clear=False):
            return monitor_mod.HermesIncidentMonitor()

    def test_owner_chat_falls_back_to_allowed_user(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SUPERVISOR_NOTIFICATION_CHAT_ID": "",
                "LOG_CHAT_ID": "",
                "ALLOWED_USER_IDS": "12345,67890",
            },
            clear=False,
        ):
            self.assertEqual(12345, monitor_mod._optional_chat_id())

    def test_healthy_container_recreation_is_not_an_incident(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            monitor = self.make_monitor(directory)
            monitor._state = {
                "probe": {
                    "container_id": "old",
                    "running": True,
                    "status": "running",
                    "health": "healthy",
                    "restart_count": 0,
                }
            }
            probe = monitor_mod.BotProbe(
                container_id="new",
                running=True,
                status="running",
                health="healthy",
                restart_count=0,
                exit_code=0,
                error=None,
            )
            self.assertIsNone(monitor._reason(probe))

    def test_restart_count_increase_is_escalated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            monitor = self.make_monitor(directory)
            monitor._state = {
                "probe": {
                    "container_id": "same",
                    "running": True,
                    "status": "running",
                    "health": "healthy",
                    "restart_count": 1,
                }
            }
            probe = monitor_mod.BotProbe(
                container_id="same",
                running=True,
                status="running",
                health="healthy",
                restart_count=2,
                exit_code=0,
                error=None,
            )
            self.assertEqual("container-auto-restarted", monitor._reason(probe))

    def test_unhealthy_requires_configured_consecutive_polls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            monitor = self.make_monitor(directory)
            monitor.unhealthy_threshold = 2
            monitor._state = {
                "probe": {
                    "container_id": "same",
                    "running": True,
                    "status": "running",
                    "health": "healthy",
                    "restart_count": 0,
                }
            }
            probe = monitor_mod.BotProbe(
                container_id="same",
                running=True,
                status="running",
                health="unhealthy",
                restart_count=0,
                exit_code=0,
                error=None,
            )
            self.assertIsNone(monitor._reason(probe))
            self.assertEqual("container-unhealthy", monitor._reason(probe))

    def test_same_event_is_blocked_during_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            monitor = self.make_monitor(directory)
            monitor._last_event_key = "same"
            monitor._last_event_at = 10_000.0
            monitor.event_cooldown_seconds = 600
            with patch.object(monitor_mod.time, "time", return_value=10_100.0):
                self.assertFalse(monitor._can_submit("same"))
                self.assertTrue(monitor._can_submit("different"))

    def test_open_incident_episode_blocks_follow_up_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            monitor = self.make_monitor(directory)
            monitor._incident_episode_open = True
            self.assertFalse(monitor._can_submit("container-unhealthy|same|2|running|unhealthy"))
            self.assertFalse(monitor._can_submit("container-not-running|same|2|exited|none"))

    def test_only_healthy_probe_closes_incident_episode(self) -> None:
        healthy = monitor_mod.BotProbe(
            container_id="same",
            running=True,
            status="running",
            health="healthy",
            restart_count=2,
            exit_code=0,
            error=None,
        )
        starting = monitor_mod.BotProbe(
            container_id="same",
            running=True,
            status="running",
            health="starting",
            restart_count=2,
            exit_code=0,
            error=None,
        )
        stopped = monitor_mod.BotProbe(
            container_id="same",
            running=False,
            status="exited",
            health=None,
            restart_count=2,
            exit_code=1,
            error=None,
        )
        self.assertTrue(monitor_mod.HermesIncidentMonitor._is_recovered(healthy))
        self.assertFalse(monitor_mod.HermesIncidentMonitor._is_recovered(starting))
        self.assertFalse(monitor_mod.HermesIncidentMonitor._is_recovered(stopped))

    def test_monitor_source_contains_only_read_only_docker_actions(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('self._compose("ps", "-q", "bot")', source)
        self.assertIn('"logs",', source)
        for forbidden in (
            'self._compose("restart"',
            'self._compose("up"',
            'self._compose("down"',
            'self._compose("stop"',
            'self._compose("rm"',
            "systemctl",
            "docker.sock",
        ):
            self.assertNotIn(forbidden, source)

    def test_systemd_unit_is_unprivileged_and_read_only(self) -> None:
        source = (
            ROOT / "deploy/systemd/velvet-hermes-incident-monitor.service"
        ).read_text(encoding="utf-8")
        self.assertIn("User=velvet", source)
        self.assertIn("NoNewPrivileges=true", source)
        self.assertIn("ProtectSystem=strict", source)
        self.assertIn("PrivateTmp=true", source)
        self.assertIn("EnvironmentFile=/srv/hermes-operator-control/incident.env", source)
        self.assertNotIn("User=root", source)
        self.assertNotIn("ExecStartPre=/usr/bin/docker", source)


if __name__ == "__main__":
    unittest.main()
