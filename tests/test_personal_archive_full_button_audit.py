from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.presentation.telegram.routers.workspace_reference_buttons import (
    _empty_reference_keyboard,
    _reference_keyboard,
)
from velvet_bot.presentation.telegram.routers.workspace_watermark_archive_only import (
    _download_policy_error,
    _watermark_prerequisite_error,
)
from velvet_bot.presentation.telegram.workspace_ui_adjustments import _media_card_keyboard
from velvet_bot.workspace_ui import (
    build_workspace_home_keyboard,
    build_workspace_member_home_keyboard,
)

ROOT = Path(__file__).resolve().parents[1]


def _labels(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


def _rows(keyboard) -> list[list[str]]:
    return [[button.text for button in row] for row in keyboard.inline_keyboard]


def _actions(keyboard, prefix: str) -> set[str]:
    return {
        str(button.callback_data).split(":", maxsplit=2)[1]
        for row in keyboard.inline_keyboard
        for button in row
        if str(button.callback_data or "").startswith(prefix + ":")
    }


def _workspace() -> Workspace:
    now = datetime.now(UTC)
    return Workspace(7, "space-7", "Личный архив", False, now, now)


def _modules(*keys: str) -> tuple[WorkspaceModuleSetting, ...]:
    now = datetime.now(UTC)
    return tuple(
        WorkspaceModuleSetting(
            workspace_id=7,
            module_key=key,  # type: ignore[arg-type]
            is_allowed=True,
            is_enabled=True,
            updated_by_user_id=1,
            created_at=now,
            updated_at=now,
        )
        for key in keys
    )


def _archive_page(*, media_type: str = "photo", image_document: bool = False):
    return SimpleNamespace(
        offset=0,
        total=2,
        character=SimpleNamespace(id=71, archive_topic_url="https://t.me/c/1/2"),
        media=SimpleNamespace(
            id=111,
            media_type=media_type,
            is_image_document=image_document,
            is_public=True,
            requires_adult_channel=False,
            is_spoiler=False,
        ),
    )


def _owner_card(*, media_type: str = "photo"):
    return _media_card_keyboard(
        _archive_page(media_type=media_type),
        workspace_id=7,
        owner_access=True,
        public_state=SimpleNamespace(
            liked_by_user=False,
            like_count=3,
            subscribed=False,
        ),
        public_enabled=True,
        has_watermark_asset=True,
        personal_like=False,
    )


class PersonalArchiveHomeAuditTests(unittest.TestCase):
    def test_owner_home_exposes_every_enabled_product_module(self) -> None:
        labels = _labels(
            build_workspace_home_keyboard(
                _workspace(),
                public_enabled=False,
                modules=_modules(
                    "characters",
                    "archive",
                    "taxonomy",
                    "references",
                    "public_archive",
                    "watermark",
                    "qwen",
                    "publications",
                    "analytics",
                    "team",
                ),
            )
        )
        for expected in (
            "🧭 Быстрые действия",
            "👥 Персонажи",
            "🖼 Архив",
            "🗂 Категории и вселенные",
            "🧬 Референсы",
            "💧 Watermark",
            "🤖 Qwen",
            "📣 Публикации",
            "📊 Аналитика",
            "👤 Команда",
            "🌐 Сделать публичным",
            "🧩 Выбрать модули",
            "✖ Закрыть",
        ):
            self.assertIn(expected, labels)

    def test_reviewer_home_only_exposes_read_and_review_tools(self) -> None:
        labels = _labels(
            build_workspace_member_home_keyboard(
                _workspace(),
                role="reviewer",
                modules=_modules(
                    "characters",
                    "archive",
                    "references",
                    "qwen",
                    "analytics",
                    "publications",
                    "watermark",
                    "team",
                ),
            )
        )
        for expected in (
            "🖼 Архив",
            "🧬 Референсы",
            "🤖 Qwen",
            "📊 Аналитика",
            "🗂 Выбрать пространство",
            "✖ Закрыть",
        ):
            self.assertIn(expected, labels)
        for forbidden in (
            "👥 Персонажи",
            "📣 Публикации",
            "💧 Watermark",
            "👤 Команда",
        ):
            self.assertNotIn(forbidden, labels)


class PersonalArchiveMediaCardAuditTests(unittest.TestCase):
    def test_owner_image_card_exposes_complete_action_matrix(self) -> None:
        keyboard = _owner_card()
        for expected in (
            "◀️",
            "▶️",
            "🤍 3",
            "🔔 Подписаться",
            "📥 Скачать оригинал",
            "⚡ Быстрый watermark",
            "🛠 Отправить на доработку",
            "🙈 Скрыть из публичного",
            "🔞 Пометить +18",
            "🌫 Включить блюр",
            "⚙️ Доступ и скачивание",
            "🤖 Qwen-проверка",
            "❓ Что делают кнопки",
            "📂 Ветка",
            "🗑 Удалить",
            "✖ Закрыть",
        ):
            self.assertIn(expected, _labels(keyboard))
        self.assertEqual(
            {
                "show",
                "noop",
                "like",
                "sub",
                "download",
                "watermark",
                "rework",
                "public",
                "adult",
                "blur",
                "settings",
                "qwen",
                "mediahelp",
                "delete",
                "close",
            },
            _actions(keyboard, "wpa"),
        )

    def test_help_is_penultimate_and_final_row_recovers_or_closes(self) -> None:
        rows = _rows(_owner_card())
        self.assertEqual(["❓ Что делают кнопки"], rows[-2])
        self.assertIn("✖ Закрыть", rows[-1])

    def test_viewer_card_hides_owner_and_qwen_actions(self) -> None:
        labels = _labels(
            _media_card_keyboard(
                _archive_page(),
                workspace_id=7,
                owner_access=False,
            )
        )
        for forbidden in (
            "📥 Скачать оригинал",
            "⚡ Быстрый watermark",
            "🛠 Отправить на доработку",
            "🤖 Qwen-проверка",
            "🗑 Удалить",
        ):
            self.assertNotIn(forbidden, labels)
        self.assertIn("✖ Закрыть", labels)

    def test_qwen_button_is_not_added_to_video_or_animation(self) -> None:
        for media_type in ("video", "animation"):
            with self.subTest(media_type=media_type):
                self.assertNotIn("🤖 Qwen-проверка", _labels(_owner_card(media_type=media_type)))


class PersonalReferenceButtonAuditTests(unittest.TestCase):
    def test_reference_card_has_full_management_and_recovery(self) -> None:
        page = SimpleNamespace(
            offset=0,
            total=2,
            character=SimpleNamespace(id=71),
            reference=SimpleNamespace(id=901),
        )
        labels = _labels(_reference_keyboard(page))
        for expected in (
            "◀️",
            "▶️",
            "➕ Добавить референс",
            "🔄 Заменить этот",
            "🗑 Удалить референс",
            "🔎 Сравнить результат",
            "↩️ К персонажам",
            "✖ Закрыть",
        ):
            self.assertIn(expected, labels)

    def test_empty_reference_card_keeps_add_and_exit(self) -> None:
        labels = _labels(_empty_reference_keyboard(71))
        self.assertIn("➕ Добавить референсы", labels)
        self.assertIn("↩️ К персонажам", labels)
        self.assertIn("✖ Закрыть", labels)


class PersonalArchivePolicyAuditTests(unittest.TestCase):
    def test_watermark_needs_module_and_asset_not_storage_destination(self) -> None:
        self.assertIsNone(
            _watermark_prerequisite_error(module_enabled=True, has_asset=True)
        )
        self.assertEqual(
            "Сначала включите модуль watermark и загрузите шаблон.",
            _watermark_prerequisite_error(module_enabled=False, has_asset=True),
        )
        self.assertEqual(
            "Сначала загрузите шаблон watermark.",
            _watermark_prerequisite_error(module_enabled=True, has_asset=False),
        )

    def test_download_policy_keeps_only_real_prerequisites(self) -> None:
        self.assertIsNone(
            _download_policy_error(
                audience="all",
                variant="watermark",
                channel_kinds=set(),
                has_watermark_asset=True,
            )
        )
        self.assertEqual(
            "Сначала загрузите шаблон watermark.",
            _download_policy_error(
                audience="all",
                variant="watermark",
                channel_kinds=set(),
                has_watermark_asset=False,
            ),
        )
        self.assertEqual(
            "Сначала подключите канал «Проверка скачивания».",
            _download_policy_error(
                audience="subscribers",
                variant="original",
                channel_kinds=set(),
                has_watermark_asset=True,
            ),
        )

    def test_high_risk_actions_run_before_generic_owner_handler(self) -> None:
        bundle = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        early = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/"
            "workspace_watermark_archive_only.py"
        ).read_text(encoding="utf-8")
        self.assertLess(
            bundle.index("workspace_watermark_archive_only_router"),
            bundle.index("workspace_owner_controls_router"),
        )
        for action in ("help", "watermark", "rework", "public"):
            self.assertIn(f'F.action == "{action}"', early)
        self.assertIn("_DOWNLOAD_POLICY_ACTIONS", early)
        self.assertIn("register_workspace_qwen(router)", early)
        self.assertIn("workspace_id=workspace.id", early)

    def test_subscription_delivery_and_open_are_workspace_scoped(self) -> None:
        dispatcher = (ROOT / "velvet_bot/app/public_notifications.py").read_text(
            encoding="utf-8"
        )
        notification_open = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/public_archive/"
            "notification_open.py"
        ).read_text(encoding="utf-8")
        self.assertIn("WorkspacePublicNotificationDispatcher", dispatcher)
        self.assertIn("public_archive_enabled", dispatcher)
        self.assertIn("workspace_id", notification_open)
        self.assertIn("select_public_workspace", notification_open)

    def test_runtime_help_only_documents_current_card_buttons(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/workspace_ui_adjustments.py"
        ).read_text(encoding="utf-8")
        help_text = source.split("async def _show_media_help", maxsplit=1)[1]
        help_text = help_text.split("def apply_workspace_ui_adjustments", maxsplit=1)[0]
        for expected in (
            "Лайк / Личная отметка",
            "Подписаться",
            "Скачать оригинал",
            "Быстрый watermark",
            "Qwen-проверка",
            "Отправить на доработку",
            "Доступ и скачивание",
            "Удалить",
            "Закрыть",
        ):
            self.assertIn(expected, help_text)
        for stale in (
            "+ Создать персонажа",
            "Сохранить / Загрузить медиа",
            "Промт</b>",
        ):
            self.assertNotIn(stale, help_text)


if __name__ == "__main__":
    unittest.main()
