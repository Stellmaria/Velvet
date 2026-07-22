from __future__ import annotations

from pathlib import Path


SERVICE_PATH = Path("velvet_bot/services/diagnostic_bundle.py")
TEST_PATH = Path("tests/test_owner_diagnostic_bundles.py")
MIGRATION_PATH = Path("migrations/911_workspace_self_delete.sql")
WORKLOG_PATH = Path(
    "docs/worklog/2026-07-22-diagnostic-hysteresis-cascade-consolidation.md"
)
TEMPORARY_PATHS = (
    Path(".github/workflows/apply-diagnostic-hysteresis-cascade.yml"),
    Path(".github/workflows/run-diagnostic-hysteresis-patch.yml"),
    Path("tools/apply_diagnostic_hysteresis_patch.py"),
)


def replace_once(source: str, old: str, new: str, *, label: str) -> str:
    if old not in source:
        raise RuntimeError(f"Patch anchor not found: {label}")
    return source.replace(old, new, 1)


def patch_service() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")

    if "_AUTO_TELEGRAM_FAILURE_THRESHOLD" not in source:
        source = replace_once(
            source,
            "_AUTO_GLOBAL_COOLDOWN = timedelta(minutes=30)\n",
            "_AUTO_GLOBAL_COOLDOWN = timedelta(minutes=30)\n"
            "_AUTO_TELEGRAM_FAILURE_THRESHOLD = 3\n",
            label="diagnostic threshold constant",
        )

    if "self._telegram_failure_streak = 0" not in source:
        source = replace_once(
            source,
            "        self._last_auto_any_at: datetime | None = None\n",
            "        self._last_auto_any_at: datetime | None = None\n"
            "        self._telegram_failure_streak = 0\n",
            label="diagnostic failure state",
        )

    if ">= _AUTO_TELEGRAM_FAILURE_THRESHOLD" not in source:
        source = replace_once(
            source,
            "        if not report.telegram_ok:\n"
            "            reasons.append(\"Telegram API недоступен\")\n",
            "        if report.telegram_ok:\n"
            "            self._telegram_failure_streak = 0\n"
            "        else:\n"
            "            self._telegram_failure_streak += 1\n"
            "            if (\n"
            "                self._telegram_failure_streak\n"
            "                >= _AUTO_TELEGRAM_FAILURE_THRESHOLD\n"
            "            ):\n"
            "                reasons.append(\n"
            "                    \"Telegram API недоступен \"\n"
            "                    f\"({_AUTO_TELEGRAM_FAILURE_THRESHOLD} проверки подряд)\"\n"
            "                )\n",
            label="telegram automatic trigger",
        )

    SERVICE_PATH.write_text(source, encoding="utf-8")


def patch_tests() -> None:
    source = TEST_PATH.read_text(encoding="utf-8")
    if "test_telegram_alert_requires_three_consecutive_failures" in source:
        return

    anchor = '\n\nif __name__ == "__main__":\n'
    tests = '''

    async def test_telegram_alert_requires_three_consecutive_failures(self) -> None:
        repository = SimpleNamespace(unacknowledged=AsyncMock(return_value=()))
        service = DiagnosticBundleService(
            incident_repository=repository,
            app_version="1.3.0",
            owner_user_ids=frozenset({100}),
        )
        system_service = SimpleNamespace(
            check=AsyncMock(
                side_effect=(
                    _report(status="failed", telegram_ok=False),
                    _report(status="failed", telegram_ok=False),
                    _report(status="failed", telegram_ok=False),
                )
            )
        )
        bot = SimpleNamespace(send_document=AsyncMock())
        worker_manager = SimpleNamespace()

        results = [
            await service.monitor_once(
                bot=bot,
                system_service=system_service,
                worker_manager=worker_manager,
            )
            for _ in range(3)
        ]

        self.assertEqual([0, 0, 1], results)
        bot.send_document.assert_awaited_once()

    async def test_successful_telegram_probe_resets_failure_streak(self) -> None:
        repository = SimpleNamespace(unacknowledged=AsyncMock(return_value=()))
        service = DiagnosticBundleService(
            incident_repository=repository,
            app_version="1.3.0",
            owner_user_ids=frozenset({100}),
        )
        system_service = SimpleNamespace(
            check=AsyncMock(
                side_effect=(
                    _report(status="failed", telegram_ok=False),
                    _report(),
                    _report(status="failed", telegram_ok=False),
                    _report(status="failed", telegram_ok=False),
                )
            )
        )
        bot = SimpleNamespace(send_document=AsyncMock())
        worker_manager = SimpleNamespace()

        results = [
            await service.monitor_once(
                bot=bot,
                system_service=system_service,
                worker_manager=worker_manager,
            )
            for _ in range(4)
        ]

        self.assertEqual([0, 0, 0, 0], results)
        bot.send_document.assert_not_awaited()
'''
    source = replace_once(source, anchor, tests + anchor, label="diagnostic test footer")
    TEST_PATH.write_text(source, encoding="utf-8")


def write_migration() -> None:
    if MIGRATION_PATH.exists():
        return
    MIGRATION_PATH.write_text(
        """ALTER TABLE characters
    DROP CONSTRAINT IF EXISTS characters_workspace_id_fkey;

ALTER TABLE characters
    ADD CONSTRAINT characters_workspace_id_fkey
    FOREIGN KEY (workspace_id)
    REFERENCES workspaces(id)
    ON DELETE CASCADE;

ALTER TABLE watermark_jobs
    DROP CONSTRAINT IF EXISTS watermark_jobs_workspace_id_fkey;

ALTER TABLE watermark_jobs
    ADD CONSTRAINT watermark_jobs_workspace_id_fkey
    FOREIGN KEY (workspace_id)
    REFERENCES workspaces(id)
    ON DELETE CASCADE;
""",
        encoding="utf-8",
    )


def write_worklog() -> None:
    WORKLOG_PATH.write_text(
        """# Сессия: устойчивость диагностики и консолидация веток

- Дата: 2026-07-22
- ID: `2026-07-22-diagnostic-hysteresis-cascade-consolidation`
- Линия/фаза: production diagnostics and workspace lifecycle
- Статус: `завершено`
- Ветка: `agent/fix-diagnostic-hysteresis-cascade`

## Цель

Не отправлять владельцу автоматический диагностический ZIP из-за одного кратковременного сбоя Telegram API и перенести на актуальный `main` оставшуюся полезную миграцию из конфликтующей ветки PR #291.

## Фактически сделано

- одиночный неуспешный Telegram health probe больше не создаёт автоматическую тревогу;
- тревога Telegram формируется только после трёх последовательных неуспешных проверок;
- успешная проверка сбрасывает накопленный счётчик;
- критические инциденты, PostgreSQL, диск, workers и backup продолжают запускать диагностику без задержки;
- добавлены regression tests для порога и сброса счётчика;
- перенесена миграция `911_workspace_self_delete.sql` с `ON DELETE CASCADE` для персонажей и watermark jobs;
- старый quick setup из PR #291 не переносился, потому что его уже заменил более новый guided onboarding в `main`;
- старое отдельное удаление пространства не переносилось, потому что актуальный owner controls уже содержит подтверждение и удаление.

## Совместимость

Формат diagnostic bundle и `.env` не меняются. Миграция additive и применяется обычным migrator перед polling.

## Проверка

Добавлены unit tests в `tests/test_owner_diagnostic_bundles.py`. Полный CI выполняется после открытия PR.
""",
        encoding="utf-8",
    )


def remove_temporary_files() -> None:
    for path in TEMPORARY_PATHS:
        path.unlink(missing_ok=True)


def main() -> None:
    patch_service()
    patch_tests()
    write_migration()
    write_worklog()
    remove_temporary_files()


if __name__ == "__main__":
    main()
