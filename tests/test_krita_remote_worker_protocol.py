from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.krita_worker.worker import WorkerSettings, build_local_request
from velvet_bot.infrastructure.krita_remote_api import KritaRemoteSettings


class KritaRemoteWorkerProtocolTests(unittest.TestCase):
    def test_build_local_request_uses_only_local_bridge_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sources" / "job.png"
            output = root / "outputs" / "job.png"
            response = root / "responses" / "job.json"
            payload = build_local_request(
                job={
                    "job_id": 41,
                    "revision": 3,
                    "remove_only": False,
                    "logo": {"kind": "builtin", "name": "Velvet"},
                    "settings": {"position": "bottom_right", "opacity": 70},
                },
                bridge_dir=root,
                source_path=source,
                output_path=output,
                response_path=response,
                local_logo=None,
            )

        self.assertEqual("wm-41-r3", payload["request_id"])
        self.assertEqual(str(root), payload["bridge_root"])
        self.assertEqual(str(source), payload["source_path"])
        self.assertEqual(str(output), payload["output_path"])
        self.assertEqual("builtin", payload["logo"]["kind"])
        self.assertNotIn("lease_token", payload)

    def test_build_local_request_requires_custom_logo_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "snapshot"):
                build_local_request(
                    job={
                        "job_id": 5,
                        "revision": 1,
                        "logo": {"kind": "workspace", "width": 100, "height": 50},
                        "settings": {},
                    },
                    bridge_dir=root,
                    source_path=root / "source.png",
                    output_path=root / "output.png",
                    response_path=root / "response.json",
                    local_logo=None,
                )

    def test_remote_server_requires_strong_token(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KRITA_REMOTE_WORKER_ENABLED": "true",
                "KRITA_REMOTE_WORKER_TOKEN": "short",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "не менее 32"):
                KritaRemoteSettings.from_env()

    def test_remote_server_defaults_to_separate_port(self) -> None:
        environment = dict(os.environ)
        environment["KRITA_REMOTE_WORKER_ENABLED"] = "false"
        environment.pop("KRITA_REMOTE_PORT", None)
        with patch.dict(os.environ, environment, clear=True):
            settings = KritaRemoteSettings.from_env()

        self.assertEqual(8766, settings.port)
        self.assertFalse(settings.enabled)

    def test_windows_worker_rejects_missing_token(self) -> None:
        environment = dict(os.environ)
        environment.pop("VELVET_KRITA_WORKER_TOKEN", None)
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "не менее 32"):
                WorkerSettings.from_env()


if __name__ == "__main__":
    unittest.main()
