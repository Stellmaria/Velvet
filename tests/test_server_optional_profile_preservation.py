from __future__ import annotations

import unittest
from pathlib import Path


class ServerOptionalProfilePreservationTests(unittest.TestCase):
    def test_deploy_core_start_does_not_prune_profile_services(self) -> None:
        source = Path("deploy/server/deploy.sh").read_text(encoding="utf-8")
        start_core = source.split("start_core_services() {", 1)[1].split("\n}", 1)[0]

        self.assertIn('"${compose[@]}" up -d postgres supervisor-proxy', start_core)
        self.assertNotIn("--remove-orphans", start_core)

    def test_systemd_start_and_reload_do_not_prune_profile_services(self) -> None:
        source = Path("deploy/systemd/velvet-compose.service").read_text(
            encoding="utf-8"
        )
        lifecycle_lines = [
            line
            for line in source.splitlines()
            if line.startswith(("ExecStart=", "ExecReload="))
        ]

        self.assertEqual(2, len(lifecycle_lines))
        for line in lifecycle_lines:
            self.assertIn("up -d postgres supervisor-proxy bot", line)
            self.assertNotIn("--remove-orphans", line)


if __name__ == "__main__":
    unittest.main()
