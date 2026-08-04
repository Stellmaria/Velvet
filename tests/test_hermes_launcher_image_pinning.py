from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "deploy" / "hermes-coders" / "pin_launcher_images.py"
VELVET_IMAGE = "sha256:" + "a" * 64
MAX_IMAGE = "sha256:" + "b" * 64


def load_module():
    spec = importlib.util.spec_from_file_location("pin_launcher_images_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load pin_launcher_images")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LauncherImagePinningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.base = root / "launcher"
        self.releases = self.base / "releases"
        self.previous = self.releases / ("1" * 40)
        self.pending = self.releases / ("2" * 40)
        for release in (self.previous, self.pending):
            release.mkdir(parents=True)
            for name in (
                "launcher.py",
                "launcher_contract.py",
                "launcher_runtime.py",
                "sandbox_entrypoint.py",
            ):
                (release / name).write_text(name, encoding="utf-8")
        self.current = self.base / "current"
        self.current.symlink_to(self.previous)
        self.env = root / "launcher.env"
        self.env.write_text(
            "HERMES_CODERS_ROOT=/srv/hermes-coders\n"
            f"HERMES_SANDBOX_INSTALL_DIR={self.current}\n"
            f"HERMES_SANDBOX_PENDING_INSTALL_DIR={self.pending}\n"
            "HERMES_SANDBOX_VELVET_IMAGE=\n"
            "HERMES_SANDBOX_MAX_IMAGE=\n"
            "HERMES_SANDBOX_NETWORK=hermes-sandbox-egress\n",
            encoding="utf-8",
        )
        self.env.chmod(0o640)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_update_records_ids_switches_release_and_preserves_mode(self) -> None:
        self.module.update(self.env, VELVET_IMAGE, MAX_IMAGE)
        text = self.env.read_text(encoding="utf-8")
        self.assertIn(f"HERMES_SANDBOX_VELVET_IMAGE={VELVET_IMAGE}", text)
        self.assertIn(f"HERMES_SANDBOX_MAX_IMAGE={MAX_IMAGE}", text)
        self.assertEqual(self.pending.resolve(), self.current.resolve())
        self.assertEqual(0o640, stat.S_IMODE(self.env.stat().st_mode))

    def test_mutable_tag_is_rejected_without_switch(self) -> None:
        with self.assertRaises(RuntimeError):
            self.module.update(self.env, "velvet:latest", MAX_IMAGE)
        self.assertEqual(self.previous.resolve(), self.current.resolve())

    def test_pending_release_outside_fixed_root_is_rejected(self) -> None:
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        text = self.env.read_text(encoding="utf-8").replace(
            str(self.pending), str(outside)
        )
        self.env.write_text(text, encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.module.update(self.env, VELVET_IMAGE, MAX_IMAGE)
        self.assertEqual(self.previous.resolve(), self.current.resolve())

    def test_failed_env_replace_restores_previous_symlink(self) -> None:
        real_replace = os.replace

        def fail_env_replace(source, destination):
            if Path(destination) == self.env:
                raise OSError("synthetic env replacement failure")
            return real_replace(source, destination)

        with patch.object(self.module.os, "replace", side_effect=fail_env_replace):
            with self.assertRaises(OSError):
                self.module.update(self.env, VELVET_IMAGE, MAX_IMAGE)
        self.assertEqual(self.previous.resolve(), self.current.resolve())
        self.assertNotIn(VELVET_IMAGE, self.env.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
