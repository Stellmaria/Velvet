from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from velvet_bot.database import Database
from velvet_bot.telegram_export_import import import_telegram_export

DEFAULT_CHANNEL_ID = -1003802812639


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Импортирует result.json или ZIP экспорта Telegram Desktop "
            "в таблицы аналитики Velvet."
        )
    )
    parser.add_argument("--file", required=True, help="Путь к result.json или ZIP")
    parser.add_argument(
        "--kind",
        required=True,
        choices=("channel", "discussion"),
        help="Тип источника",
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        help="Telegram chat ID. Для основного канала по умолчанию используется Velvet.",
    )
    parser.add_argument(
        "--parent-channel-id",
        type=int,
        default=DEFAULT_CHANNEL_ID,
        help="Канал, к которому относится обсуждение",
    )
    parser.add_argument(
        "--database-url",
        help="Строка PostgreSQL. По умолчанию берётся DATABASE_URL из .env",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    load_dotenv()
    database_url = args.database_url or os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("Не задан DATABASE_URL в аргументе или .env.")

    path = Path(args.file).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")

    raw = path.read_bytes()
    target_chat_id = args.chat_id
    if args.kind == "channel" and target_chat_id is None:
        target_chat_id = DEFAULT_CHANNEL_ID

    database = Database(database_url)
    await database.initialize()
    try:
        summary = await import_telegram_export(
            database,
            raw=raw,
            file_name=path.name,
            source_kind=args.kind,
            target_chat_id=target_chat_id,
            parent_channel_id=(
                args.parent_channel_id if args.kind == "discussion" else None
            ),
            imported_by=None,
        )
    finally:
        await database.close()

    print("Импорт завершён")
    print(f"Источник: {summary.source_name}")
    print(f"Тип: {summary.source_kind}")
    print(f"Chat ID: {summary.source_chat_id}")
    print(f"Записей: {summary.total_records}")
    print(f"Сообщений: {summary.imported_messages}")
    print(f"Публикаций/альбомов: {summary.publication_count}")
    print(f"Промтов: {summary.prompt_publications}")
    print(f"Хэштегов: {summary.hashtag_count}")
    print(f"Персонажей сопоставлено: {summary.character_matches}")
    print(f"Реакций: {summary.reaction_count}")
    if summary.duplicate_import:
        print("Файл уже импортировался ранее, данные не дублировались.")


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
