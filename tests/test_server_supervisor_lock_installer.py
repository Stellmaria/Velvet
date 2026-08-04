from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "deploy/server/install-server-supervisor.sh"


class ServerSupervisorLockInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.installer = INSTALLER.read_text(encoding="utf-8")

    def test_installer_serializes_against_active_deploy(self) -> None:
        self.assertIn(
            'DEPLOY_LOCK="${VELVET_DEPLOY_LOCK:-${TMPDIR:-/tmp}/velvet-deploy.lock}"',
            self.installer,
        )
        self.assertIn('exec 9>"$DEPLOY_LOCK"', self.installer)
        self.assertIn("flock -n 9", self.installer)
        self.assertIn("exit 75", self.installer)

    def test_installer_repairs_lock_for_unprivileged_supervisor(self) -> None:
        self.assertIn('chown velvet:velvet "$DEPLOY_LOCK"', self.installer)
        self.assertIn('chmod 0600 "$DEPLOY_LOCK"', self.installer)
        self.assertIn(
            "Refusing unexpected Velvet deploy lock path",
            self.installer,
        )
        self.assertNotIn('chmod 0666 "$DEPLOY_LOCK"', self.installer)


if __name__ == "__main__":
    unittest.main()
