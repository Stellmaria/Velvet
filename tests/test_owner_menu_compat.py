from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest


class OwnerMenuCompatibilityTests(unittest.TestCase):
    def test_every_admin_root_has_exactly_one_owner_home_button(self) -> None:
        script = textwrap.dedent(
            r'''
            from velvet_bot.presentation.telegram.router import get_root_router
            from velvet_bot.owner_menu_compat import install_owner_menu_navigation
            from velvet_bot.quality_audit import QualitySummary

            # Build the real composition root and repeat installation to prove
            # that compatibility wrapping is idempotent.
            get_root_router()
            install_owner_menu_navigation()
            install_owner_menu_navigation()

            from velvet_bot.presentation.telegram.routers.characters import directory as admin_directory
            from velvet_bot.presentation.telegram.routers.analytics_controllers import dashboard as analytics_dashboard
            from velvet_bot.presentation.telegram.routers.quality_operations_controllers import backup_center
            from velvet_bot.presentation.telegram.routers.publication import center as publication_center
            from velvet_bot.presentation.telegram.routers import system as system_center
            import velvet_bot.quality_ui as quality_ui

            summary = QualitySummary(
                pending_duplicates=0,
                confirmed_duplicates=0,
                pending_scans=0,
                scan_errors=0,
                broken_files=0,
                unchecked_files=0,
                missing_category=0,
                missing_universe=0,
                missing_story=0,
                empty_characters=0,
                media_without_prompt=0,
                orphan_media=0,
                unresolved_hashtags=0,
            )

            keyboards = {
                "characters": admin_directory._category_keyboard([]),
                "analytics": analytics_dashboard._main_keyboard("all"),
                "backups": backup_center._main_keyboard(),
                "publications": publication_center._center_keyboard(),
                "system": system_center._main_keyboard(),
                "quality": quality_ui.build_quality_dashboard(summary)[1],
            }

            for name, keyboard in keyboards.items():
                values = [
                    button.callback_data
                    for row in keyboard.inline_keyboard
                    for button in row
                    if button.callback_data is not None
                ]
                count = values.count("own:menu")
                if count != 1:
                    raise AssertionError(
                        f"{name}: expected one own:menu callback, got {count}: {values}"
                    )
                for value in values:
                    if len(value.encode("utf-8")) > 64:
                        raise AssertionError(
                            f"{name}: Telegram callback limit exceeded: {value}"
                        )
            '''
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=(
                "Isolated owner-menu composition check failed.\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
