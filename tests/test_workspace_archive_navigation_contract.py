from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiogram.types import Message

from velvet_bot.domains.public_archive.models import PublicMediaState
from velvet_bot.presentation.telegram.workspace_archive_navigation import (
    WorkspaceArchiveCardContext,
    build_workspace_archive_navigation,
    format_workspace_archive_caption,
    send_workspace_archive_page,
)
from velvet_bot.presentation.telegram.workspace_archive_navigation_controller import (
    handle_workspace_archive_navigation,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
)

ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "velvet_bot/presentation/telegram"


def _page(*, total: int = 3, offset: int = 1):
    return SimpleNamespace(
        character=SimpleNamespace(
            id=17,
            archive_topic_url="https://t.me/c/1/2",
        ),
        media=SimpleNamespace(
            id=31,
            telegram_file_id="file-31",
            media_type="photo",
            is_public=False,
            requires_adult_channel=True,
            is_spoiler=True,
            is_image_document=False,
            file_size=1024,
        ),
        offset=offset,
        total=total,
    )


def _labels(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


def _callbacks(keyboard) -> list[str]:
    return [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]


class WorkspaceArchiveNavigationPresentationTests(unittest.IsolatedAsyncioTestCase):
    def test_owner_keyboard_preserves_navigation_and_media_actions(self) -> None:
        page = _page()
        state = PublicMediaState(
            like_count=4,
            liked_by_user=True,
            subscribed=False,
        )

        keyboard = build_workspace_archive_navigation(
            page,  # type: ignore[arg-type]
            workspace_id=9,
            owner_access=True,
            public_state=state,
            public_enabled=True,
            has_watermark_asset=True,
            personal_like=False,
        )
        labels = _labels(keyboard)
        callbacks = _callbacks(keyboard)

        self.assertIn("2 / 3", labels)
        self.assertIn("❤️ 4", labels)
        self.assertIn("🔔 Подписаться", labels)
        self.assertIn("⚡ Быстрый watermark", labels)
        self.assertIn("👁 Вернуть в публичный", labels)
        self.assertIn("🔞 Снять +18", labels)
        self.assertIn("🌫 Убрать блюр", labels)
        self.assertIn("📂 Ветка", labels)
        self.assertIn("🗑 Удалить", labels)
        self.assertIn("✖ Закрыть", labels)
        self.assertIn("wpa:show:9:17:0:31", callbacks)
        self.assertIn("wpa:show:9:17:2:31", callbacks)
        self.assertIn("wpa:settings:9:17:1:31", callbacks)

    def test_viewer_keyboard_hides_owner_actions(self) -> None:
        keyboard = build_workspace_archive_navigation(
            _page(total=1, offset=0),  # type: ignore[arg-type]
            workspace_id=9,
            owner_access=False,
        )
        labels = _labels(keyboard)

        self.assertEqual("1 / 1", labels[0])
        self.assertIn("📂 Ветка", labels)
        self.assertIn("✖ Закрыть", labels)
        self.assertNotIn("🗑 Удалить", labels)
        self.assertNotIn("📥 Скачать оригинал", labels)
        self.assertNotIn("⚙️ Доступ и скачивание", labels)

    def test_oversized_image_document_caption_keeps_warning(self) -> None:
        page = _page(total=1, offset=0)
        page.media.is_image_document = True
        page.media.file_size = 21 * 1024 * 1024

        with patch(
            "velvet_bot.presentation.telegram.workspace_archive_navigation."
            "format_archive_caption",
            return_value="Базовая подпись",
        ):
            caption = format_workspace_archive_caption(page)  # type: ignore[arg-type]

        self.assertIn("Базовая подпись", caption)
        self.assertIn("Файл больше 20 МБ", caption)
        self.assertIn("кнопкой «Скачать»", caption)

    async def test_send_photo_preserves_protected_content_and_markup(self) -> None:
        page = _page(total=1, offset=0)
        sent = Mock(spec=Message)
        bot = SimpleNamespace(
            send_photo=AsyncMock(return_value=sent),
            send_video=AsyncMock(),
            send_animation=AsyncMock(),
            send_document=AsyncMock(),
        )
        context = WorkspaceArchiveCardContext(
            public_state=None,
            public_enabled=False,
            has_watermark_asset=False,
            personal_like=False,
        )

        with (
            patch(
                "velvet_bot.presentation.telegram.workspace_archive_navigation."
                "load_workspace_archive_card_context",
                new=AsyncMock(return_value=context),
            ),
            patch(
                "velvet_bot.presentation.telegram.workspace_archive_navigation."
                "format_archive_caption",
                return_value="Подпись",
            ),
        ):
            result = await send_workspace_archive_page(
                bot,  # type: ignore[arg-type]
                database=SimpleNamespace(),  # type: ignore[arg-type]
                workspace_product_service=SimpleNamespace(),  # type: ignore[arg-type]
                chat_id=55,
                user_id=77,
                workspace_id=9,
                page=page,  # type: ignore[arg-type]
                owner_access=False,
            )

        self.assertIs(sent, result)
        bot.send_photo.assert_awaited_once()
        kwargs = bot.send_photo.await_args.kwargs
        self.assertEqual(55, kwargs["chat_id"])
        self.assertEqual("file-31", kwargs["photo"])
        self.assertEqual("Подпись", kwargs["caption"])
        self.assertTrue(kwargs["protect_content"])
        self.assertIsNotNone(kwargs["reply_markup"])
        bot.send_video.assert_not_awaited()
        bot.send_animation.assert_not_awaited()
        bot.send_document.assert_not_awaited()


class WorkspaceArchiveNavigationControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_deletes_message_without_workspace_resolution(self) -> None:
        message = Mock(spec=Message)
        message.delete = AsyncMock()
        callback = SimpleNamespace(
            message=message,
            answer=AsyncMock(),
            from_user=SimpleNamespace(id=77),
        )
        action = WorkspacePersonalArchiveAction(
            action="close",
            workspace_id=9,
            character_id=17,
            offset=1,
            media_id=31,
        )
        workspace_service = SimpleNamespace(
            set_active_workspace=AsyncMock(),
            resolve_active_workspace=AsyncMock(),
            require_role=AsyncMock(),
        )

        await handle_workspace_archive_navigation(
            callback,  # type: ignore[arg-type]
            action,
            SimpleNamespace(),  # type: ignore[arg-type]
            SimpleNamespace(),  # type: ignore[arg-type]
            workspace_service,  # type: ignore[arg-type]
            SimpleNamespace(),  # type: ignore[arg-type]
        )

        message.delete.assert_awaited_once_with()
        callback.answer.assert_awaited_once_with()
        workspace_service.set_active_workspace.assert_not_awaited()
        workspace_service.resolve_active_workspace.assert_not_awaited()
        workspace_service.require_role.assert_not_awaited()


class WorkspaceArchiveNavigationBoundaryTests(unittest.TestCase):
    def test_navigation_layer_has_no_owner_controls_dependency(self) -> None:
        presentation = (
            PRESENTATION / "workspace_archive_navigation.py"
        ).read_text(encoding="utf-8")
        controller = (
            PRESENTATION / "workspace_archive_navigation_controller.py"
        ).read_text(encoding="utf-8")

        self.assertIn("build_workspace_archive_navigation", presentation)
        self.assertIn("send_workspace_archive_page", presentation)
        self.assertIn("replace_workspace_archive_page", presentation)
        self.assertIn("WorkspacePersonalArchiveActionFilter", controller)
        self.assertIn('"open", "show", "close", "empty", "help"', controller)
        self.assertNotIn("workspace_owner_controls", presentation)
        self.assertNotIn("workspace_owner_controls", controller)
        self.assertNotIn("@router.callback_query", controller)

    def test_archive_registrar_installs_navigation_before_owner_router(self) -> None:
        registrar = (
            PRESENTATION / "workspace_archive_dashboard_controller.py"
        ).read_text(encoding="utf-8")
        bundle = (
            PRESENTATION / "routers/archive_and_public.py"
        ).read_text(encoding="utf-8")

        navigation = registrar.index("register_workspace_archive_navigation(router)")
        policy = registrar.index("register_workspace_media_policy(router)")
        self.assertLess(navigation, policy)

        registration = bundle.index("register_workspace_archive_dashboard(router)")
        owner = bundle.index("router.include_router(workspace_owner_controls_router)")
        self.assertLess(registration, owner)


if __name__ == "__main__":
    unittest.main()
