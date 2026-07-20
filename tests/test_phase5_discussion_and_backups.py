import unittest
from unittest.mock import AsyncMock, patch

from velvet_bot.backup_runtime import BackupService as RuntimeBackupService
from velvet_bot.backup_service import (
    BackupError,
    BackupService as BaseBackupService,
    parse_pg_restore_tables,
    select_retained_paths,
)
from velvet_bot.discussion_insights import format_delay
from velvet_bot.presentation.telegram.routers.analytics_controllers.discussion_overrides import (
    DiscussionInsightCallback,
    _dcb,
)
from velvet_bot.presentation.telegram.routers.quality_operations_controllers.backup_center import (
    BackupCallback,
)


class DiscussionInsightTests(unittest.TestCase):
    def test_delay_formatting(self) -> None:
        self.assertEqual("—", format_delay(None))
        self.assertEqual("45 сек.", format_delay(45))
        self.assertEqual("2 мин.", format_delay(120))
        self.assertEqual("2 ч. 5 мин.", format_delay(7500))
        self.assertEqual("2 д. 3 ч.", format_delay(183600))

    def test_discussion_callbacks_stay_inside_telegram_limit(self) -> None:
        values = [
            _dcb(
                "stories",
                period="30d",
                chat_id=-1003859952761,
                parent_id=-1003802812639,
                page=999999,
                item_id=9223372036854775807,
            ),
            DiscussionInsightCallback(
                action="activity",
                period="all",
                chat_id=-1003859952761,
                page=999999,
                item_id=9223372036854775807,
            ).pack(),
        ]
        for value in values:
            self.assertLessEqual(len(value.encode("utf-8")), 64, value)

    def test_backup_callbacks_stay_inside_telegram_limit(self) -> None:
        value = BackupCallback(
            action="retention-plus",
            page=999999,
            backup_id=9223372036854775807,
        ).pack()
        self.assertLessEqual(len(value.encode("utf-8")), 64)


class BackupHelperTests(unittest.TestCase):
    def test_parse_pg_restore_tables_deduplicates_table_and_data_entries(self) -> None:
        output = """
        203; 1259 18001 TABLE public characters velvet
        204; 0 18001 TABLE DATA public characters velvet
        205; 1259 18002 TABLE public channel_posts velvet
        206; 0 18002 TABLE DATA public channel_posts velvet
        207; 1259 18003 SEQUENCE public characters_id_seq velvet
        """
        self.assertEqual(
            ("channel_posts", "characters"),
            parse_pg_restore_tables(output),
        )

    def test_rotation_retains_newest_files_only(self) -> None:
        records = [
            (5, "five.dump"),
            (4, "four.dump"),
            (3, None),
            (2, "two.dump"),
            (1, "one.dump"),
        ]
        kept, deleted = select_retained_paths(records, 3)
        self.assertEqual({5, 4, 2}, kept)
        self.assertEqual({1}, deleted)

    def test_rotation_never_keeps_fewer_than_three(self) -> None:
        records = [(number, f"{number}.dump") for number in range(5, 0, -1)]
        kept, deleted = select_retained_paths(records, 1)
        self.assertEqual({5, 4, 3}, kept)
        self.assertEqual({2, 1}, deleted)


class BackupRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self) -> RuntimeBackupService:
        return RuntimeBackupService(
            database_url="postgresql://test:test@localhost/test",
            backup_dir="backups-test",
            pg_dump_path="missing-pg-dump",
            pg_restore_path="missing-pg-restore",
        )

    async def test_missing_pg_dump_skips_optional_startup_backup(self) -> None:
        service = self.make_service()
        missing = BackupError(
            "Не найден pg_dump. Укажите путь в .env или добавьте утилиты PostgreSQL в PATH."
        )
        with patch.object(
            BaseBackupService,
            "prepare_pre_migration_backup",
            new=AsyncMock(side_effect=missing),
        ):
            self.assertFalse(await service.prepare_pre_migration_backup())

    async def test_other_startup_backup_errors_are_not_hidden(self) -> None:
        service = self.make_service()
        with patch.object(
            BaseBackupService,
            "prepare_pre_migration_backup",
            new=AsyncMock(side_effect=BackupError("PostgreSQL недоступен.")),
        ):
            with self.assertRaisesRegex(BackupError, "PostgreSQL недоступен"):
                await service.prepare_pre_migration_backup()


if __name__ == "__main__":
    unittest.main()
