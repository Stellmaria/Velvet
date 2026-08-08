from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "deploy/hermes-librarian/recreate_bot_preserving_image.sh"
LIFECYCLE_SCRIPTS = (
    ROOT / "deploy/hermes-librarian/enable_afk.sh",
    ROOT / "deploy/hermes-librarian/enable_full_archive.sh",
    ROOT / "deploy/hermes-librarian/disable_afk.sh",
)


class ArthurLifecycleImagePreservationTests(unittest.TestCase):
    def test_lifecycle_scripts_use_shared_image_preserving_recreate(self) -> None:
        for path in LIFECYCLE_SCRIPTS:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn(
                    "bash deploy/hermes-librarian/recreate_bot_preserving_image.sh",
                    source,
                )
                self.assertNotIn("up -d --force-recreate bot", source)

    def test_helper_preserves_exact_running_image_id_and_fails_closed(self) -> None:
        source = HELPER.read_text(encoding="utf-8")

        self.assertIn('ps -q bot', source)
        self.assertIn("Bot container отсутствует", source)
        self.assertIn("{{.State.Running}}", source)
        self.assertIn("{{.Image}}", source)
        self.assertIn('^sha256:[0-9a-f]{64}$', source)
        self.assertIn('docker image tag "$current_image_id" "$preserved_image_ref"', source)
        self.assertIn('VELVET_IMAGE="$preserved_image_ref"', source)
        self.assertIn('up -d --no-deps --force-recreate bot', source)
        self.assertIn('if [[ "$new_image_id" != "$current_image_id" ]]', source)
        self.assertIn("Arthur lifecycle image mismatch", source)


if __name__ == "__main__":
    unittest.main()
