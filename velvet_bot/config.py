import os
from dataclasses import dataclass

from dotenv import load_dotenv

from velvet_bot.access import normalize_username


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_url: str
    allowed_user_ids: frozenset[int]
    allowed_usernames: frozenset[str]


def _parse_allowed_user_ids(value: str) -> frozenset[int]:
    result: set[int] = set()
    for item in value.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        try:
            result.add(int(cleaned))
        except ValueError as error:
            raise RuntimeError(
                "ALLOWED_USER_IDS должен содержать Telegram ID через запятую."
            ) from error
    return frozenset(result)


def _parse_allowed_usernames(value: str) -> frozenset[str]:
    return frozenset(
        username
        for item in value.split(",")
        if (username := normalize_username(item))
    )


def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env "
            "и вставьте токен, полученный у @BotFather."
        )

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "Не задан DATABASE_URL. Укажите строку подключения PostgreSQL "
            "в локальном файле .env."
        )

    allowed_user_ids = _parse_allowed_user_ids(
        os.getenv("ALLOWED_USER_IDS", "")
    )
    raw_usernames = os.getenv("ALLOWED_USERNAMES")
    if raw_usernames is None:
        raw_usernames = "va_stellmaria"
    allowed_usernames = _parse_allowed_usernames(raw_usernames)

    if not allowed_user_ids and not allowed_usernames:
        raise RuntimeError(
            "Не задан владелец бота. Укажите ALLOWED_USER_IDS или "
            "ALLOWED_USERNAMES в .env."
        )

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        allowed_user_ids=allowed_user_ids,
        allowed_usernames=allowed_usernames,
    )
