import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from velvet_bot.access import normalize_username


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_url: str
    allowed_user_ids: frozenset[int]
    allowed_usernames: frozenset[str]
    log_chat_id: int | None
    analytics_channel_ids: frozenset[int]
    publication_timezone: str


def _parse_integer_list(value: str, *, variable_name: str) -> frozenset[int]:
    result: set[int] = set()
    for item in value.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        try:
            result.add(int(cleaned))
        except ValueError as error:
            raise RuntimeError(
                f"{variable_name} должен содержать числовые Telegram ID через запятую."
            ) from error
    return frozenset(result)


def _parse_allowed_user_ids(value: str) -> frozenset[int]:
    return _parse_integer_list(value, variable_name="ALLOWED_USER_IDS")


def _parse_allowed_usernames(value: str) -> frozenset[str]:
    return frozenset(
        username
        for item in value.split(",")
        if (username := normalize_username(item))
    )


def _parse_optional_chat_id(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError as error:
        raise RuntimeError("LOG_CHAT_ID должен быть числовым Telegram chat ID.") from error


def _parse_timezone(value: str) -> str:
    cleaned = value.strip() or "Europe/Berlin"
    try:
        ZoneInfo(cleaned)
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(
            "PUBLICATION_TIMEZONE должен быть корректным IANA-часовым поясом, "
            "например Europe/Berlin."
        ) from error
    return cleaned


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

    log_chat_id = _parse_optional_chat_id(
        os.getenv("LOG_CHAT_ID", "-5367533184")
    )
    analytics_channel_ids = _parse_integer_list(
        os.getenv("ANALYTICS_CHANNEL_IDS", "-1003802812639"),
        variable_name="ANALYTICS_CHANNEL_IDS",
    )
    publication_timezone = _parse_timezone(
        os.getenv("PUBLICATION_TIMEZONE", "Europe/Berlin")
    )

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        allowed_user_ids=allowed_user_ids,
        allowed_usernames=allowed_usernames,
        log_chat_id=log_chat_id,
        analytics_channel_ids=analytics_channel_ids,
        publication_timezone=publication_timezone,
    )
