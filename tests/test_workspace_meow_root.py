from __future__ import annotations

import unittest

from velvet_bot.presentation.telegram.routers.workspace_auf_root import (
    build_auf_root_keyboard,
)


def _labels(keyboard) -> list[str]:
    return [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]


class WorkspaceMeowRootContractTests(unittest.TestCase):
    def test_root_uses_photo_and_video_labels(self) -> None:
        self.assertEqual(
            ["Фото", "Видео", "↩️ Моё пространство"],
            _labels(build_auf_root_keyboard(workspace_id=9, enabled=True)),
        )


if __name__ == "__main__":
    unittest.main()
