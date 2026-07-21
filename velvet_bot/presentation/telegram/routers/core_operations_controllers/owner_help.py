from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name=__name__)

_HELP_PAGE_LIMIT = 3800

OWNER_COMMAND_GROUPS: tuple[
    tuple[str, tuple[tuple[str, str], ...]], ...
] = (
    (
        "Навигация и публичный архив",
        (
            ("start", "открыть главное меню"),
            ("help", "показать полный справочник владельца"),
            ("menu", "открыть центр управления"),
            ("admin", "алиас центра управления"),
            ("archive", "открыть выбранный публичный архив персонажей"),
            ("gallery", "алиас публичного архива"),
        ),
    ),
    (
        "Личные пространства",
        (
            ("workspace_grant", "выдать Telegram ID право создать личный архив"),
            ("workspace_revoke", "отозвать неиспользованное право создания"),
            ("workspace_module", "разрешить или запретить модуль пространства"),
            ("wcatalog", "открыть taxonomy-каталог активного личного пространства"),
            ("workspace_catalog", "алиас taxonomy-каталога пространства"),
        ),
    ),
    (
        "Персонажи, категории и истории",
        (
            ("characters", "открыть каталог персонажей"),
            ("create", "создать персонажа"),
            ("crete", "совместимый алиас создания персонажа"),
            ("topic", "назначить персонажу тему архива"),
            ("character", "открыть карточку персонажа"),
            ("category", "изменить пол или состав персонажа"),
            ("cat", "алиас изменения категории"),
            ("universe", "изменить вселенную персонажа"),
            ("world", "алиас изменения вселенной"),
            ("series", "алиас изменения вселенной"),
            ("story", "назначить персонажу историю"),
            ("stories", "показать истории вселенной"),
            ("storylist", "алиас списка историй"),
            ("storyadd", "добавить историю во вселенную"),
            ("prompt", "привязать промт к персонажу или медиа"),
            ("setprompt", "алиас привязки промта"),
        ),
    ),
    (
        "Медиа, референсы и алиасы",
        (
            ("save", "сохранить медиа персонажа"),
            ("save18", "сохранить медиа со спойлером"),
            ("savecancel", "отменить ожидание файла для сохранения"),
            ("watermark", "открыть обработку водяного знака"),
            ("refadd", "начать загрузку референсов"),
            ("refs", "показать референсы персонажа"),
            ("ref", "алиас просмотра референсов"),
            ("refdel", "удалить референс по номеру"),
            ("refdone", "завершить загрузку референсов"),
            ("refcancel", "отменить загрузку референсов"),
            ("compare_ref", "сравнить результат с референсом"),
            ("compare_reference", "алиас сравнения с референсом"),
            ("aliasadd", "добавить алиас персонажа"),
            ("tagadd", "алиас добавления тега"),
            ("aliases", "показать алиасы персонажа"),
            ("tags", "алиас просмотра тегов"),
            ("aliasdel", "удалить алиас персонажа"),
            ("tagdel", "алиас удаления тега"),
            ("aliasreindex", "пересобрать индекс алиасов"),
            ("tagreindex", "алиас пересборки индекса тегов"),
        ),
    ),
    (
        "Аналитика, обсуждения и импорт",
        (
            ("analytics", "открыть аналитический центр"),
            ("analyticsmenu", "алиас аналитического центра"),
            ("channelstats", "показать статистику канала"),
            ("stats", "алиас статистики канала"),
            ("promptstats", "показать статистику промтов"),
            ("characterstats", "показать статистику персонажей"),
            ("tagstats", "показать статистику хэштега"),
            ("hashtagstats", "алиас статистики хэштега"),
            ("trackdiscussion", "подключить чат обсуждения"),
            ("discussionstats", "показать статистику обсуждения"),
            ("importchannel", "импортировать экспорт канала Telegram"),
            ("importdiscussion", "импортировать экспорт обсуждения"),
        ),
    ),
    (
        "Публикации",
        (
            ("publish", "открыть центр публикаций"),
            ("publishing", "алиас центра публикаций"),
            ("publications", "алиас центра публикаций"),
            ("checkpost", "проверить пост и создать черновик"),
        ),
    ),
    (
        "Velvet AI и контроль качества",
        (
            ("quality", "открыть контроль качества"),
            ("auditarchive", "алиас архивного аудита"),
            ("qwen_calibration", "открыть калибровку Qwen"),
            ("qcalibration", "алиас калибровки Qwen"),
            ("analyze_set", "проанализировать целостность медиасета"),
            ("qwen_set", "алиас анализа медиасета"),
            ("rework", "открыть очередь доработки"),
            ("reworks", "алиас очереди доработки"),
            ("quality_rework", "алиас очереди доработки"),
        ),
    ),
    (
        "Система, диагностика и резервные копии",
        (
            ("system", "открыть системный центр"),
            ("health", "алиас проверки состояния системы"),
            ("version", "показать версию приложения и схемы"),
            ("diag", "открыть диагностику и кнопки ZIP-выгрузки"),
            ("diagnostics", "алиас диагностического центра"),
            ("diag_export", "собрать безопасный ZIP за 1h/6h/24h/3d/7d"),
            ("backup", "открыть центр резервных копий"),
            ("test_error_alert", "создать тестовую ошибку для проверки оповещений"),
        ),
    ),
    (
        "Supervisor, Git и Codex",
        (
            ("supervisor", "открыть Supervisor"),
            ("status", "показать состояние Supervisor"),
            ("logs", "показать логи бота"),
            ("restart", "перезапустить процесс бота"),
            ("update", "обновить проект из main"),
            ("rollback", "откатить последнее обновление"),
            ("codex", "открыть задачи Codex"),
            ("codex_status", "показать статус задачи Codex"),
            ("console", "открыть консоль Supervisor"),
            ("supervisor_console", "алиас консоли Supervisor"),
            ("supervisor_self", "управление процессом Supervisor"),
        ),
    ),
    (
        "Telegram Storage и watermark-хранилище",
        (
            ("storage", "открыть Telegram Storage Center"),
            ("storage_center", "алиас Telegram Storage Center"),
            ("storage_migrate", "запустить перенос локальных файлов"),
            ("storage_find", "найти объект в Telegram Storage"),
            ("storage_download", "скачать объект Storage по ID"),
            ("wm_file", "показать watermark-файл по media_id"),
            ("wm_storage", "алиас поиска watermark-файла"),
            ("wm_download", "скачать watermark-файл по media_id"),
        ),
    ),
)

OWNER_HELP_COMMANDS = frozenset(
    command
    for _, entries in OWNER_COMMAND_GROUPS
    for command, _ in entries
)


def build_owner_help_pages() -> tuple[str, ...]:
    intro = (
        "<b>📋 Все команды Velvet</b>\n\n"
        "Справочник доступен только создателю бота. Алиасы перечислены отдельно, "
        "чтобы было видно всё, что реально принимает код.\n"
    )
    pages: list[str] = []
    current = intro

    for title, entries in OWNER_COMMAND_GROUPS:
        block_lines = ["", f"<b>{title}</b>"]
        block_lines.extend(
            f"<code>/{command}</code> — {description}"
            for command, description in entries
        )
        block = "\n".join(block_lines)
        if len(current) + len(block) > _HELP_PAGE_LIMIT and current != intro:
            pages.append(current)
            current = intro + block
        else:
            current += block

    pages.append(current)
    total = len(pages)
    return tuple(
        f"{page}\n\n<i>Страница {index} из {total} · команд: {len(OWNER_HELP_COMMANDS)}</i>"
        for index, page in enumerate(pages, start=1)
    )


async def handle_owner_help(message: Message) -> None:
    for page in build_owner_help_pages():
        await message.answer(page)


router.message.register(handle_owner_help, Command("help"))


__all__ = (
    "OWNER_COMMAND_GROUPS",
    "OWNER_HELP_COMMANDS",
    "build_owner_help_pages",
    "handle_owner_help",
    "router",
)
