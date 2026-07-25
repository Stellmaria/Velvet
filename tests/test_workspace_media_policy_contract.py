from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.presentation.telegram.workspace_media_policy_controller import (
    build_workspace_media_policy_keyboard,
    build_workspace_media_policy_presentation,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    parse_workspace_personal_archive_callback,
    workspace_personal_archive_callback,
)

ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "velvet_bot/presentation/telegram"


def _labels(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


class WorkspacePersonalArchiveCallbackContractTests(unittest.TestCase):
    def test_callback_round_trip_preserves_all_archive_coordinates(self) -> None:
        payload = workspace_personal_archive_callback(
            "settings",
            workspace_id=9,
            character_id=17,
            offset=4,
            media_id=31,
        )

        parsed = parse_workspace_personal_archive_callback(payload)

        self.assertEqual("wpa:settings:9:17:4:31", payload)
        self.assertEqual(
            "wpa:show:9:17:0:31",
            workspace_personal_archive_callback(
                "show",
                workspace_id=9,
                character_id=17,
                offset=-4,
                media_id=31,
            ),
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(
            ("settings", 9, 17, 4, 31),
            (
                parsed.action,
                parsed.workspace_id,
                parsed.character_id,
                parsed.offset,
                parsed.media_id,
            ),
        )

    def test_parser_rejects_invalid_or_negative_payloads(self) -> None:
        self.assertIsNone(parse_workspace_personal_archive_callback("wpa:settings:9"))
        self.assertIsNone(
            parse_workspace_personal_archive_callback("wpa:settings:9:17:-1:31")
        )
        self.assertIsNone(
            parse_workspace_personal_archive_callback("other:settings:9:17:0:31")
        )


class WorkspaceMediaPolicyPresentationTests(unittest.IsolatedAsyncioTestCase):
    def test_keyboard_preserves_policy_choices_and_return_navigation(self) -> None:
        keyboard = build_workspace_media_policy_keyboard(
            workspace_id=9,
            character_id=17,
            offset=4,
            media_id=31,
            download_audience="subscribers",
            download_variant="watermark",
        )
        labels = _labels(keyboard)
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]

        self.assertIn("✅ 🔐 Подписчики канала", labels)
        self.assertIn("✅ 🖼 Только с watermark", labels)
        self.assertIn("↩️ К материалу", labels)
        self.assertIn("wpa:dlaudsub:9:17:4:31", callbacks)
        self.assertIn("wpa:dlvarwm:9:17:4:31", callbacks)
        self.assertIn("wpa:show:9:17:4:31", callbacks)

    async def test_presentation_reports_connected_policy_dependencies(self) -> None:
        service = SimpleNamespace(
            get_settings=AsyncMock(
                return_value=SimpleNamespace(
                    public_archive_enabled=True,
                    download_audience="all",
                    download_variant="original",
                )
            ),
            list_channels=AsyncMock(
                return_value=[
                    SimpleNamespace(kind="download"),
                    SimpleNamespace(kind="adult"),
                ]
            ),
        )
        workspace = SimpleNamespace(id=9, name="Мой архив")
        page = SimpleNamespace(
            character=SimpleNamespace(id=17),
            media=SimpleNamespace(id=31),
            offset=4,
        )
        onboarding = SimpleNamespace(
            list_destinations=AsyncMock(
                return_value=[
                    SimpleNamespace(destination_key="characters"),
                    SimpleNamespace(destination_key="watermarks"),
                ]
            )
        )
        watermark = SimpleNamespace(get=AsyncMock(return_value=object()))

        with (
            patch(
                "velvet_bot.presentation.telegram.workspace_media_policy_controller."
                "WorkspaceOnboardingRepository",
                return_value=onboarding,
            ),
            patch(
                "velvet_bot.presentation.telegram.workspace_media_policy_controller."
                "WorkspaceWatermarkAssetRepository",
                return_value=watermark,
            ),
        ):
            presentation = await build_workspace_media_policy_presentation(
                SimpleNamespace(),  # type: ignore[arg-type]
                workspace_product_service=service,  # type: ignore[arg-type]
                workspace=workspace,  # type: ignore[arg-type]
                page=page,  # type: ignore[arg-type]
            )

        self.assertIn("Доступ к медиа · Мой архив", presentation.text)
        self.assertIn("Канал проверки скачивания: <b>подключён</b>", presentation.text)
        self.assertIn("Watermark-копии: <b>назначение подключено</b>", presentation.text)
        self.assertIn("Шаблон watermark: <b>настроен</b>", presentation.text)


class WorkspaceMediaPolicyBoundaryTests(unittest.TestCase):
    def test_archive_dashboard_no_longer_imports_owner_controls(self) -> None:
        source = (PRESENTATION / "workspace_archive_dashboard.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("workspace_personal_archive_callback", source)
        self.assertNotIn("workspace_owner_controls", source)
        self.assertNotIn("WorkspacePersonalArchiveCallback", source)

    def test_policy_controller_owns_settings_help_and_download_policy(self) -> None:
        source = (PRESENTATION / "workspace_media_policy_controller.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("build_workspace_media_policy_presentation", source)
        self.assertIn("handle_workspace_media_policy", source)
        self.assertIn("set_download_policy", source)
        self.assertIn('"settings"', source)
        self.assertIn('"mediahelp"', source)
        self.assertIn('"dlaudsub"', source)
        self.assertIn('"dlvarwm"', source)
        self.assertNotIn("workspace_owner_controls", source)
        self.assertNotIn("@router.callback_query", source)

    def test_archive_registrar_registers_policy_before_owner_router(self) -> None:
        controller = (
            PRESENTATION / "workspace_archive_dashboard_controller.py"
        ).read_text(encoding="utf-8")
        bundle = (
            PRESENTATION / "routers/archive_and_public.py"
        ).read_text(encoding="utf-8")

        self.assertIn("register_workspace_media_policy(router)", controller)
        registration = bundle.index("register_workspace_archive_dashboard(router)")
        owner = bundle.index("router.include_router(workspace_owner_controls_router)")
        self.assertLess(registration, owner)


if __name__ == "__main__":
    unittest.main()
