from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "deploy/hermes-monitor"


def _load_host_module():
    spec = importlib.util.spec_from_file_location("host_monitor", BASE / "host_monitor.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HermesMonitorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.host = (BASE / "host_monitor.py").read_text(encoding="utf-8")
        cls.gateway = (BASE / "gateway.py").read_text(encoding="utf-8")
        cls.client = (BASE / "monitorctl.py").read_text(encoding="utf-8")
        cls.compose = (BASE / "compose.yaml").read_text(encoding="utf-8")
        cls.installer = (BASE / "install.sh").read_text(encoding="utf-8")
        cls.host_unit = (ROOT / "deploy/systemd/hermes-operator-monitor.service").read_text(encoding="utf-8")
        cls.gateway_unit = (ROOT / "deploy/systemd/hermes-monitor-gateway.service").read_text(encoding="utf-8")
        cls.module = _load_host_module()

    def test_fixed_views_are_exact_and_shared(self) -> None:
        expected = {"summary", "resources", "containers", "services", "gpu", "models", "processes", "incidents"}
        self.assertEqual(set(self.module._ALLOWED_VIEWS), expected)
        for value in expected:
            self.assertIn(f'"{value}"', self.gateway)
            self.assertIn(f'"{value}"', self.client)

    def test_host_request_accepts_only_token_and_view(self) -> None:
        self.assertIn('set(payload) != {"token", "view"}', self.host)
        self.assertNotIn('payload.get("command")', self.host)
        self.assertNotIn('payload.get("path")', self.host)
        self.assertNotIn('payload.get("unit")', self.host)
        self.assertNotIn('payload.get("pid")', self.host)

    def test_subprocesses_are_shell_free(self) -> None:
        self.assertIn("subprocess.run(", self.host)
        self.assertNotIn("shell=True", self.host)
        self.assertNotIn("os.system", self.host)
        self.assertNotIn("Popen(", self.host)

    def test_process_view_does_not_collect_command_line(self) -> None:
        self.assertIn('"pid=,user=,comm=,%cpu=,%mem=,etimes=,stat="', self.host)
        self.assertNotIn("cmdline", self.host.lower())
        self.assertNotIn("args=", self.host)

    def test_docker_view_excludes_sensitive_inspect_fields(self) -> None:
        self.assertIn('["docker", "ps", "-a"', self.host)
        self.assertIn("{{json .State}}", self.host)
        for forbidden in (".Config.Env", ".Config.Cmd", ".Mounts", ".Config.Labels"):
            self.assertNotIn(forbidden, self.host)

    def test_gateway_is_get_only_and_has_no_query_parameters(self) -> None:
        self.assertIn("def do_GET", self.gateway)
        self.assertIn("def do_POST", self.gateway)
        self.assertIn("Read-only gateway", self.gateway)
        self.assertIn('"?" in self.path', self.gateway)
        self.assertNotIn("subprocess", self.gateway)

    def test_gateway_container_is_internal_and_hardened(self) -> None:
        self.assertNotIn("ports:", self.compose)
        self.assertNotIn("docker.sock", self.compose)
        self.assertIn("read_only: true", self.compose)
        self.assertIn("cap_drop:\n      - ALL", self.compose)
        self.assertIn("no-new-privileges:true", self.compose)
        self.assertIn('user: "10001:${HERMES_OPS_SOCKET_GID:-10001}"', self.compose)
        self.assertIn("velvet-backend", self.compose)

    def test_host_and_gateway_units_are_separated(self) -> None:
        self.assertIn("User=root", self.host_unit)
        self.assertIn("Group=velvet", self.host_unit)
        self.assertIn("ProtectSystem=strict", self.host_unit)
        self.assertIn("ReadWritePaths=/run/hermes-operator-monitor", self.host_unit)
        self.assertIn("User=velvet", self.gateway_unit)
        self.assertIn("hermes-operator-monitor.service", self.gateway_unit)
        self.assertNotIn("User=root", self.gateway_unit)

    def test_installer_preserves_separate_monitor_token(self) -> None:
        self.assertIn('values.get("HERMES_OPS_MONITOR_TOKEN", "")', self.installer)
        self.assertIn("secrets.token_urlsafe(48)", self.installer)
        self.assertIn("without printing secret values", self.installer)
        self.assertIn("monitorctl.py", self.installer)
        self.assertIn("monitorctl.py summary", self.installer)
        self.assertNotIn("command_allowlist", self.installer)

    def test_client_uses_dedicated_token_file_and_fixed_path(self) -> None:
        self.assertIn("/opt/data/.hermes-ops-client-token", self.client)
        self.assertIn("/v1/monitor/{args.view}", self.client)
        self.assertNotIn("--command", self.client)
        self.assertNotIn("--unit", self.client)
        self.assertNotIn("--pid", self.client)

    def test_redaction_removes_common_secret_shapes(self) -> None:
        redact = self.module._redact
        samples = (
            "token=abcdef0123456789",
            "Authorization: Bearer abcdef0123456789",
            "https://user:password@example.invalid/path",
            "github_pat_abcdefghijklmnopqrstuvwxyz1234567890",
            "A" * 60,
        )
        for sample in samples:
            redacted = redact(sample)
            self.assertIn("REDACTED", redacted)
            self.assertNotIn("password@example", redacted)

    def test_meminfo_parser_converts_kib_to_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meminfo"
            path.write_text("MemTotal: 1024 kB\nMemAvailable: 512 kB\n", encoding="utf-8")
            parsed = self.module._read_meminfo(path)
        self.assertEqual(parsed["MemTotal"], 1024 * 1024)
        self.assertEqual(parsed["MemAvailable"], 512 * 1024)

    def test_unknown_view_is_rejected_without_dispatch(self) -> None:
        old = os.environ.get("HERMES_OPS_MONITOR_TOKEN")
        os.environ["HERMES_OPS_MONITOR_TOKEN"] = "x" * 32
        try:
            runtime = self.module.MonitorRuntime()
            result = runtime.collect("arbitrary")
        finally:
            if old is None:
                os.environ.pop("HERMES_OPS_MONITOR_TOKEN", None)
            else:
                os.environ["HERMES_OPS_MONITOR_TOKEN"] = old
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "unknown_view")

    def test_fixed_service_inventory_has_no_user_supplied_units(self) -> None:
        self.assertIn('"romatic-server-supervisor.service"', self.host)
        self.assertIn('"velvet-hermes-incident-monitor.service"', self.host)
        self.assertIn("for unit in _FIXED_UNITS", self.host)
        self.assertNotIn("services(self, unit", self.host)


if __name__ == "__main__":
    unittest.main()
