from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.public_archive import PublicArchiveRepository
from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    _archive_navigation,
    _media_settings_keyboard,
    _send_owner_original,
)
from velvet_bot.presentation.telegram.workspace_public_access import (
    has_workspace_adult_access,
    has_workspace_download_access,
)


ROOT = Path(__file__).resolve().parents[1]


def _texts(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


class WorkspaceOwnerMediaKeyboardTests(unittest.TestCase):
    @staticmethod
    def _page():
        return SimpleNamespace(
            offset=0,
            total=1,
            character=SimpleNamespace(id=7, archive_topic_url="https://t.me/c/1/2"),
            media=SimpleNamespace(
                id=11,
                is_public=True,
                requires_adult_channel=False,
                is_spoiler=False,
            ),
        )

    def test_owner_card_exposes_complete_media_control_matrix(self) -> None:
        state = SimpleNamespace(liked_by_user=False, like_count=4, subscribed=False)

        keyboard = _archive_navigation(
            self._page(),
            workspace_id=5,
            owner_access=True,
            public_state=state,
            public_enabled=True,
            has_watermark_asset=True,
        )

        labels = _texts(keyboard)
        for expected in (
            "🤍 4",
            "🔔 Подписаться",
            "❓ Что делают кнопки",
            "📥 Скачать оригинал",
            "⚡ Быстрый watermark",
            "🛠 Отправить на доработку",
            "🙈 Скрыть из публичного",
            "🔞 Пометить +18",
            "🌫 Включить блюр",
            "⚙️ Доступ и скачивание",
        ):
            self.assertIn(expected, labels)

    def test_team_viewer_does_not_receive_owner_actions(self) -> None:
        keyboard = _archive_navigation(
            self._page(),
            workspace_id=5,
            owner_access=False,
        )

        labels = _texts(keyboard)
        self.assertNotIn("📥 Скачать оригинал", labels)
        self.assertNotIn("🗑 Удалить", labels)
        self.assertIn("✖ Закрыть", labels)

    def test_download_settings_offer_all_policy_modes_and_setup_links(self) -> None:
        labels = _texts(
            _media_settings_keyboard(
                workspace_id=5,
                character_id=7,
                offset=0,
                media_id=11,
                download_audience="disabled",
                download_variant="watermark",
            )
        )
        self.assertIn("✅ 🚫 Никто", labels)
        self.assertIn("🌐 Все читатели", labels)
        self.assertIn("🔐 Подписчики канала", labels)
        self.assertIn("✅ 🖼 Только с watermark", labels)
        self.assertIn("📦 Оригинал", labels)
        self.assertIn("🔌 Каналы доступа", labels)

    def test_private_owner_like_is_presented_as_personal_mark(self) -> None:
        state = SimpleNamespace(liked_by_user=True, like_count=99, subscribed=False)

        labels = _texts(
            _archive_navigation(
                self._page(),
                workspace_id=5,
                owner_access=True,
                public_state=state,
                personal_like=True,
            )
        )

        self.assertIn("❤️ Личная отметка", labels)
        self.assertNotIn("❤️ 99", labels)


class WorkspacePublicAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_personal_adult_access_uses_workspace_adult_channel(self) -> None:
        product = SimpleNamespace(
            list_channels=AsyncMock(
                return_value=(SimpleNamespace(kind="adult", chat_id=-10077),)
            )
        )
        bot = SimpleNamespace()
        with patch(
            "velvet_bot.presentation.telegram.workspace_public_access."
            "has_adult_channel_access",
            new=AsyncMock(return_value=True),
        ) as membership:
            allowed = await has_workspace_adult_access(
                bot=bot,
                user_id=42,
                workspace_id=5,
                manager_access=False,
                default_adult_channel_id=-1001,
                workspace_product_service=product,
            )

        self.assertTrue(allowed)
        membership.assert_awaited_once_with(
            bot,
            42,
            channel_id=-10077,
        )

    async def test_subscription_download_checks_selected_download_channel(self) -> None:
        product = SimpleNamespace(
            get_settings=AsyncMock(
                return_value=SimpleNamespace(download_audience="subscribers")
            ),
            list_channels=AsyncMock(
                return_value=(SimpleNamespace(kind="download", chat_id=-10088),)
            ),
        )
        bot = SimpleNamespace()
        with patch(
            "velvet_bot.presentation.telegram.workspace_public_access."
            "has_adult_channel_access",
            new=AsyncMock(return_value=True),
        ) as membership:
            allowed = await has_workspace_download_access(
                bot=bot,
                user_id=42,
                workspace_id=5,
                member_access=False,
                manager_access=False,
                workspace_product_service=product,
            )

        self.assertTrue(allowed)
        membership.assert_awaited_once_with(bot, 42, channel_id=-10088)


class _Acquire:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class WorkspaceDownloadPolicyTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _repository(
        audience: str,
        variant: str = "watermark",
        *,
        watermark_ready: bool = True,
    ):
        connection = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "telegram_file_id": "watermarked-file",
                    "source_telegram_file_id": "original-file",
                    "watermark_applied": watermark_ready,
                    "watermark_approved": watermark_ready,
                    "download_audience": audience,
                    "download_variant": variant,
                }
            ),
        )
        database = SimpleNamespace(acquire=lambda: _Acquire(connection))
        return PublicArchiveRepository(database, workspace_id=5)

    async def test_audience_and_variant_are_independent(self) -> None:
        disabled = await self._repository("disabled").resolve_download_source(
            character_id=7, media_id=11, member_access=False
        )
        original = await self._repository("all", "original").resolve_download_source(
            character_id=7, media_id=11, member_access=False
        )
        watermark = await self._repository("all", "watermark").resolve_download_source(
            character_id=7, media_id=11, member_access=False
        )
        denied_subscription = await self._repository(
            "subscribers", "watermark"
        ).resolve_download_source(
            character_id=7,
            media_id=11,
            member_access=False,
            download_access=False,
        )
        allowed_subscription = await self._repository(
            "subscribers", "watermark"
        ).resolve_download_source(
            character_id=7,
            media_id=11,
            member_access=False,
            download_access=True,
        )

        self.assertIsNone(disabled)
        self.assertEqual(
            ("original-file", "original"),
            (original.telegram_file_id, original.variant),
        )
        self.assertEqual(
            ("watermarked-file", "watermarked"),
            (watermark.telegram_file_id, watermark.variant),
        )
        self.assertIsNone(denied_subscription)
        self.assertEqual(
            ("watermarked-file", "watermarked"),
            (allowed_subscription.telegram_file_id, allowed_subscription.variant),
        )

    async def test_owner_original_uses_preserved_source_after_watermark(self) -> None:
        bot = SimpleNamespace(send_document=AsyncMock())
        media = SimpleNamespace(
            media_type="document",
            telegram_file_id="watermarked-file",
            source_telegram_file_id="original-file",
        )

        await _send_owner_original(bot, user_id=42, media=media)

        bot.send_document.assert_awaited_once_with(
            chat_id=42,
            document="original-file",
            caption="Оригинал из вашего личного архива",
        )


class WorkspaceMediaControlsContractTests(unittest.TestCase):
    def test_new_migration_extends_download_mode_without_editing_old_migration(self) -> None:
        original = (ROOT / "migrations/901_workspaces.sql").read_text(encoding="utf-8")
        migration = (
            ROOT / "migrations/912_workspace_media_access_controls.sql"
        ).read_text(encoding="utf-8")
        self.assertNotIn("subscription", original)
        self.assertIn("'subscription'", migration)
        self.assertIn("workspace_settings_downloads_mode_check", migration)

    def test_personal_cards_are_protected_and_rework_remains_publicly_hidden(self) -> None:
        owner = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_owner_controls.py"
        ).read_text(encoding="utf-8")
        visibility = (
            ROOT / "velvet_bot/domains/public_archive/visibility.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"protect_content": True', owner)
        self.assertIn("media_rework_items AS active_rework", visibility)
        manual = (
            ROOT / "velvet_bot/domains/media_rework/manual.py"
        ).read_text(encoding="utf-8")
        self.assertIn("скрыта из", owner)
        self.assertIn("SET is_public = FALSE", manual)
        self.assertIn("MediaReworkRepository(database).is_active", owner)

    def test_workspace_fast_watermark_snapshots_workspace_and_logo(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/public_archive/"
            "watermark_actions.py"
        ).read_text(encoding="utf-8")
        self.assertIn("workspace_id=workspace_id", source)
        self.assertIn("logo_kind=(logo_asset.asset_kind", source)
        self.assertIn("logo_path=(logo_asset.local_path", source)

    def test_owner_help_explains_creation_prompt_batch_and_media_controls(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_owner_controls.py"
        ).read_text(encoding="utf-8")
        for phrase in (
            "+ Создать персонажа",
            "пакетную загрузку",
            "Промт",
            "не заменяя оригинал",
            "владелец возвращает работу",
        ):
            self.assertIn(phrase, source)

    def test_alignment_migration_adds_independent_policy_and_destinations(self) -> None:
        migration = (
            ROOT / "migrations/913_workspace_media_contract_alignment.sql"
        ).read_text(encoding="utf-8")
        for token in (
            "download_audience",
            "download_variant",
            "'downloads'",
            "'watermarks'",
            "workspace_media_owner_favorites",
        ):
            self.assertIn(token, migration)


if __name__ == "__main__":
    unittest.main()
