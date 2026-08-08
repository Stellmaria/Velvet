from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ServerHousekeepingContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prune = (ROOT / "deploy/server/prune-build-cache.sh").read_text(
            encoding="utf-8"
        )
        self.installer = (
            ROOT / "deploy/server/install-build-cache-prune.sh"
        ).read_text(encoding="utf-8")
        self.service = (
            ROOT / "deploy/systemd/velvet-build-cache-prune.service"
        ).read_text(encoding="utf-8")
        self.timer = (
            ROOT / "deploy/systemd/velvet-build-cache-prune.timer"
        ).read_text(encoding="utf-8")

    def test_prune_is_conservative_and_serialized_with_deploy(self) -> None:
        self.assertIn('${TMPDIR:-/tmp}/velvet-deploy.lock', self.prune)
        self.assertIn("flock -n 9", self.prune)
        self.assertIn("Skipping BuildKit cache prune", self.prune)
        self.assertIn('VELVET_BUILD_CACHE_PRUNE_AGE:-168h', self.prune)
        self.assertIn('builder prune -af --filter "until=$PRUNE_AGE"', self.prune)
        self.assertNotIn("docker system prune", self.prune)
        self.assertNotIn("image prune", self.prune)
        self.assertNotIn("volume prune", self.prune)

    def test_prune_service_runs_unprivileged_and_shares_host_tmp(self) -> None:
        self.assertIn("User=velvet", self.service)
        self.assertIn("Group=velvet", self.service)
        self.assertIn("ExecStart=/usr/bin/bash /srv/velvet/deploy/server/prune-build-cache.sh", self.service)
        self.assertIn("Environment=VELVET_BUILD_CACHE_PRUNE_AGE=168h", self.service)
        self.assertIn("NoNewPrivileges=true", self.service)
        self.assertIn("ProtectSystem=strict", self.service)
        self.assertIn("ReadWritePaths=/tmp", self.service)
        self.assertNotIn("PrivateTmp=true", self.service)
        self.assertNotIn("User=root", self.service)

    def test_prune_timer_is_weekly_persistent_and_jittered(self) -> None:
        self.assertIn("OnCalendar=Sun *-*-* 04:15:00 UTC", self.timer)
        self.assertIn("RandomizedDelaySec=30m", self.timer)
        self.assertIn("Persistent=true", self.timer)
        self.assertIn("Unit=velvet-build-cache-prune.service", self.timer)
        self.assertIn("WantedBy=timers.target", self.timer)

    def test_installer_only_enables_timer(self) -> None:
        self.assertIn("install -m 0644", self.installer)
        self.assertIn("systemctl daemon-reload", self.installer)
        self.assertIn(
            "systemctl enable --now velvet-build-cache-prune.timer", self.installer
        )
        self.assertNotIn(
            "systemctl enable --now velvet-build-cache-prune.service", self.installer
        )

    def test_housekeeping_shell_scripts_parse_with_bash(self) -> None:
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")
        for relative in (
            "deploy/server/prune-build-cache.sh",
            "deploy/server/install-build-cache-prune.sh",
        ):
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                result = subprocess.run(
                    [bash, "-n"],
                    input=source,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    0,
                    result.returncode,
                    (result.stderr or result.stdout).strip(),
                )


if __name__ == "__main__":
    unittest.main()
