from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from velvet_bot.core.access import normalize_username


DEFAULT_AI_VISION_MODEL = "gemma3:4b"


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_url: str
    allowed_user_ids: frozenset[int]
    allowed_usernames: frozenset[str]
    log_chat_id: int | None
    analytics_channel_ids: frozenset[int]
    publication_timezone: str
    backup_dir: str
    pg_dump_path: str
    pg_restore_path: str
    ai_vision_enabled: bool = False
    ai_vision_provider: str = "ollama"
    ai_vision_base_url: str = "http://127.0.0.1:11434"
    ai_vision_model: str = DEFAULT_AI_VISION_MODEL
    ai_vision_api_key: str | None = None
    ai_vision_timeout_seconds: int = 180
    ai_vision_max_attempts: int = 3


def parse_integer_list(value: str, *, variable_name: str) -> frozenset[int]:
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


def parse_allowed_user_ids(value: str) -> frozenset[int]:
    return parse_integer_list(value, variable_name="ALLOWED_USER_IDS")


def parse_allowed_usernames(value: str) -> frozenset[str]:
    return frozenset(
        username
        for item in value.split(",")
        if (username := normalize_username(item))
    )


def parse_optional_chat_id(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError as error:
        raise RuntimeError("LOG_CHAT_ID должен быть числовым Telegram chat ID.") from error


def parse_boolean(value: str, *, variable_name: str) -> bool:
    cleaned = value.strip().casefold()
    if cleaned in {"1", "true", "yes", "on", "да"}:
        return True
    if cleaned in {"0", "false", "no", "off", "нет", ""}:
        return False
    raise RuntimeError(
        f"{variable_name} должен быть true/false, yes/no, on/off или 1/0."
    )


def parse_bounded_integer(
    value: str,
    *,
    variable_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    cleaned = value.strip()
    if not cleaned:
        return default
    try:
        result = int(cleaned)
    except ValueError as error:
        raise RuntimeError(f"{variable_name} должен быть целым числом.") from error
    if not minimum <= result <= maximum:
        raise RuntimeError(
            f"{variable_name} должен быть от {minimum} до {maximum}."
        )
    return result


def parse_timezone(value: str) -> str:
    cleaned = value.strip() or "Europe/Berlin"
    try:
        ZoneInfo(cleaned)
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(
            "PUBLICATION_TIMEZONE должен быть корректным IANA-часовым поясом, "
            "например Europe/Berlin."
        ) from error
    return cleaned


def parse_required_path(value: str, *, default: str, variable_name: str) -> str:
    cleaned = value.strip() or default
    if "\x00" in cleaned:
        raise RuntimeError(f"{variable_name} содержит недопустимый путь.")
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

    allowed_user_ids = parse_allowed_user_ids(
        os.getenv("ALLOWED_USER_IDS", "")
    )
    raw_usernames = os.getenv("ALLOWED_USERNAMES")
    if raw_usernames is None:
        raw_usernames = "va_stellmaria"
    allowed_usernames = parse_allowed_usernames(raw_usernames)

    if not allowed_user_ids and not allowed_usernames:
        raise RuntimeError(
            "Не задан владелец бота. Укажите ALLOWED_USER_IDS или "
            "ALLOWED_USERNAMES в .env."
        )

    ai_provider = os.getenv("AI_VISION_PROVIDER", "ollama").strip().casefold()
    if ai_provider not in {"ollama", "openai_compatible"}:
        raise RuntimeError(
            "AI_VISION_PROVIDER должен быть ollama или openai_compatible."
        )
    ai_base_url = os.getenv(
        "AI_VISION_BASE_URL",
        "http://127.0.0.1:11434",
    ).strip().rstrip("/")
    if not ai_base_url:
        raise RuntimeError("AI_VISION_BASE_URL не может быть пустым.")
    ai_model = os.getenv("AI_VISION_MODEL", DEFAULT_AI_VISION_MODEL).strip()
    if not ai_model:
        raise RuntimeError("AI_VISION_MODEL не может быть пустым.")
    ai_api_key = os.getenv("AI_VISION_API_KEY", "").strip() or None

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        allowed_user_ids=allowed_user_ids,
        allowed_usernames=allowed_usernames,
        log_chat_id=parse_optional_chat_id(os.getenv("LOG_CHAT_ID", "-5367533184")),
        analytics_channel_ids=parse_integer_list(
            os.getenv("ANALYTICS_CHANNEL_IDS", "-1003802812639"),
            variable_name="ANALYTICS_CHANNEL_IDS",
        ),
        publication_timezone=parse_timezone(
            os.getenv("PUBLICATION_TIMEZONE", "Europe/Berlin")
        ),
        backup_dir=parse_required_path(
            os.getenv("BACKUP_DIR", "backups"),
            default="backups",
            variable_name="BACKUP_DIR",
        ),
        pg_dump_path=parse_required_path(
            os.getenv("PG_DUMP_PATH", "pg_dump"),
            default="pg_dump",
            variable_name="PG_DUMP_PATH",
        ),
        pg_restore_path=parse_required_path(
            os.getenv("PG_RESTORE_PATH", "pg_restore"),
            default="pg_restore",
            variable_name="PG_RESTORE_PATH",
        ),
        ai_vision_enabled=parse_boolean(
            os.getenv("AI_VISION_ENABLED", "false"),
            variable_name="AI_VISION_ENABLED",
        ),
        ai_vision_provider=ai_provider,
        ai_vision_base_url=ai_base_url,
        ai_vision_model=ai_model,
        ai_vision_api_key=ai_api_key,
        ai_vision_timeout_seconds=parse_bounded_integer(
            os.getenv("AI_VISION_TIMEOUT_SECONDS", "180"),
            variable_name="AI_VISION_TIMEOUT_SECONDS",
            default=180,
            minimum=10,
            maximum=600,
        ),
        ai_vision_max_attempts=parse_bounded_integer(
            os.getenv("AI_VISION_MAX_ATTEMPTS", "3"),
            variable_name="AI_VISION_MAX_ATTEMPTS",
            default=3,
            minimum=1,
            maximum=10,
        ),
    )


__all__ = (
    "DEFAULT_AI_VISION_MODEL",
    "Settings",
    "load_settings",
    "parse_allowed_user_ids",
    "parse_allowed_usernames",
    "parse_boolean",
    "parse_bounded_integer",
    "parse_integer_list",
    "parse_optional_chat_id",
    "parse_required_path",
    "parse_timezone",
)
