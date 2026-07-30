from __future__ import annotations

import json
import unittest
from pathlib import Path


class ServerDockerDaemonContractTests(unittest.TestCase):
    def test_log_rotation_and_live_restore_are_enabled(self) -> None:
        payload = json.loads(
            Path("deploy/server/docker-daemon.json.example").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("json-file", payload["log-driver"])
        self.assertEqual("20m", payload["log-opts"]["max-size"])
        self.assertGreaterEqual(int(payload["log-opts"]["max-file"]), 3)
        self.assertTrue(payload["live-restore"])


if __name__ == "__main__":
    unittest.main()
