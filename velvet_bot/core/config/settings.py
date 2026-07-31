from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from velvet_bot.core.access import normalize_username

DEFAULT_ADULT_CHANNEL_ID = -1003951213065
LOCAL_OPENAI_COMPATIBLE_PROVIDER = "local_openai_compatible"
_LOCAL_VISION_HOSTS = frozenset({"vision-gateway"})
_VISION_PROVIDERS = frozenset(
    {"ollama", "openai_compatible", LOCAL_OPENAI_COMPATIBLE_PROVIDER}
)
_TEXT_PROVIDERS = frozenset({"ollama", "openai", "openai_compatible"})


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
    ai_vision_provider: str = "openai_compatible"
    ai_vision_base_url: str = "https://byesu.com/v1"
    ai_vision_model: str = ""
    ai_vision_compare_model: str | None = None
    ai_vision_fallback_model: str | None = None
    ai_vision_api_key: str | None = None
    ai_vision_timeout_seconds: int = 180
    ai_vision_max_attempts: int = 3
    ai_text_enabled: bool = False
    ai_text_provider: str = "openai_compatible"
    ai_text_base_url: str = "https://byesu.com/v1"
    ai_text_model: str | None = None
    ai_text_api_key: str | None = None
    ai_text_timeout_seconds: int = 180
    ai_text_max_attempts: int = 2
    ai_text_max_output_tokens: int = 1800
    ai_text_max_history_messages: int = 30
    ai_text_fallback_provider: str | None = None
    ai_text_fallback_base_url: str = "https://byesu.com/v1"
    ai_text_fallback_model: str | None = None
    ai_text_fallback_api_key: str | None = None
    moderator_user_ids: frozenset[int] = frozenset()
    adult_channel_id: int = DEFAULT_ADULT_CHANNEL_ID


@dataclass(frozen=True, slots=True)
class _VisionSettings:
    enabled: bool
    provider: str
    base_url: str
    model: str
    compare_model: str | None
    fallback_model: str | None
    api_key: str | None
    timeout_seconds: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class _TextSettings:
    enabled: bool
    provider: str
    base_url: str
    model: str | None
    api_key: str | None
    timeout_seconds: int
    max_attempts: int
    max_output_tokens: int
    max_history_messages: int
    fallback_provider: str | None
    fallback_base_url: str
    fallback_model: str | None
    fallback_api_key: str | None


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
        username for item in value.split(",")
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


def parse_chat_id(value: str, *, variable_name: str, default: int) -> int:
    cleaned = value.strip()
    if not cleaned:
        return int(default)
    try:
        return int(cleaned)
    except ValueError as error:
        raise RuntimeError(
            f"{variable_name} должен быть числовым Telegram chat ID."
        ) from error


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


def _parse_ai_provider(
    value: str,
    *,
    variable_name: str,
    allowed: frozenset[str],
    optional: bool = False,
) -> str | None:
    provider = value.strip().casefold()
    if optional and not provider:
        return None
    if provider not in allowed:
        choices = ", ".join(sorted(allowed))
        raise RuntimeError(f"{variable_name} должен быть одним из: {choices}.")
    return provider


def _parse_ai_base_url(value: str, *, variable_name: str) -> str:
    result = value.strip().rstrip("/")
    if not result:
        raise RuntimeError(f"{variable_name} не может быть пустым.")
    return result


def validate_local_vision_base_url(
    provider: str,
    base_url: str,
    *,
    variable_name: str,
) -> None:
    """Reject SSRF-prone endpoints for the trusted internal VL provider."""

    if provider != LOCAL_OPENAI_COMPATIBLE_PROVIDER:
        return
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(
            f"{variable_name} для локального VL должен использовать http:// или https://."
        )
    if parsed.username or parsed.password:
        raise RuntimeError(
            f"{variable_name} для локального VL не может содержать credentials."
        )
    if parsed.hostname not in _LOCAL_VISION_HOSTS:
        allowed = ", ".join(sorted(_LOCAL_VISION_HOSTS))
        raise RuntimeError(
            f"{variable_name} для локального VL должен использовать внутренний "
            f"Compose host: {allowed}."
        )
    if parsed.query or parsed.fragment:
        raise RuntimeError(
            f"{variable_name} для локального VL не может содержать query или fragment."
        )


def _shared_cloud_api_key() -> str:
    return (
        os.getenv("BYESU_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def _provider_needs_api_key(provider: str | None) -> bool:
    return provider in {"openai", "openai_compatible"}


def _load_vision_settings(shared_cloud_key: str) -> _VisionSettings:
    enabled = parse_boolean(
        os.getenv("AI_VISION_ENABLED", "false"),
        variable_name="AI_VISION_ENABLED",
    )
    provider = _parse_ai_provider(
        os.getenv("AI_VISION_PROVIDER", "openai_compatible"),
        variable_name="AI_VISION_PROVIDER",
        allowed=_VISION_PROVIDERS,
    )
    assert provider is not None
    base_url = _parse_ai_base_url(
        os.getenv("AI_VISION_BASE_URL", "https://byesu.com/v1"),
        variable_name="AI_VISION_BASE_URL",
    )
    validate_local_vision_base_url(
        provider,
        base_url,
        variable_name="AI_VISION_BASE_URL",
    )
    model = os.getenv("AI_VISION_MODEL", "").strip()
    api_key = (
        os.getenv("AI_VISION_API_KEY", "").strip()
        or shared_cloud_key
        or None
    )
    if enabled and not model:
        raise RuntimeError("AI_VISION_ENABLED=true требует непустой AI_VISION_MODEL.")
    if enabled and _provider_needs_api_key(provider) and not api_key:
        raise RuntimeError(
            "Для облачного AI_VISION_PROVIDER задайте AI_VISION_API_KEY, "
            "BYESU_API_KEY или OPENAI_API_KEY."
        )
    return _VisionSettings(
        enabled=enabled,
        provider=provider,
        base_url=base_url,
        model=model,
        compare_model=os.getenv("AI_VISION_COMPARE_MODEL", "").strip() or None,
        fallback_model=os.getenv("AI_VISION_FALLBACK_MODEL", "").strip() or None,
        api_key=api_key,
        timeout_seconds=parse_bounded_integer(
            os.getenv("AI_VISION_TIMEOUT_SECONDS", "180"),
            variable_name="AI_VISION_TIMEOUT_SECONDS",
            default=180,
            minimum=10,
            maximum=600,
        ),
        max_attempts=parse_bounded_integer(
            os.getenv("AI_VISION_MAX_ATTEMPTS", "3"),
            variable_name="AI_VISION_MAX_ATTEMPTS",
            default=3,
            minimum=1,
            maximum=10,
        ),
    )


def _load_text_settings(shared_cloud_key: str) -> _TextSettings:
    enabled = parse_boolean(
        os.getenv("AI_TEXT_ENABLED", "false"),
        variable_name="AI_TEXT_ENABLED",
    )
    provider = _parse_ai_provider(
        os.getenv("AI_TEXT_PROVIDER", "openai_compatible"),
        variable_name="AI_TEXT_PROVIDER",
        allowed=_TEXT_PROVIDERS,
    )
    assert provider is not None
    base_default = (
        "https://api.openai.com/v1"
        if provider == "openai"
        else "https://byesu.com/v1"
    )
    base_url = _parse_ai_base_url(
        os.getenv("AI_TEXT_BASE_URL", base_default),
        variable_name="AI_TEXT_BASE_URL",
    )
    model = os.getenv("AI_TEXT_MODEL", "").strip() or None
    api_key = os.getenv("AI_TEXT_API_KEY", "").strip() or shared_cloud_key or None
    if enabled and not model:
        raise RuntimeError("AI_TEXT_ENABLED=true требует непустой AI_TEXT_MODEL.")
    if enabled and _provider_needs_api_key(provider) and not api_key:
        raise RuntimeError(
            "Для облачного AI_TEXT_PROVIDER задайте AI_TEXT_API_KEY, "
            "BYESU_API_KEY или OPENAI_API_KEY."
        )

    fallback_provider = _parse_ai_provider(
        os.getenv("AI_TEXT_FALLBACK_PROVIDER", ""),
        variable_name="AI_TEXT_FALLBACK_PROVIDER",
        allowed=_TEXT_PROVIDERS,
        optional=True,
    )
    fallback_model = os.getenv("AI_TEXT_FALLBACK_MODEL", "").strip() or None
    if bool(fallback_provider) != bool(fallback_model):
        raise RuntimeError(
            "AI_TEXT_FALLBACK_PROVIDER и AI_TEXT_FALLBACK_MODEL должны быть "
            "заданы вместе."
        )
    fallback_default = (
        "https://api.openai.com/v1"
        if fallback_provider == "openai"
        else "https://byesu.com/v1"
    )
    fallback_base_url = _parse_ai_base_url(
        os.getenv("AI_TEXT_FALLBACK_BASE_URL", fallback_default),
        variable_name="AI_TEXT_FALLBACK_BASE_URL",
    )
    fallback_api_key = (
        os.getenv("AI_TEXT_FALLBACK_API_KEY", "").strip()
        or shared_cloud_key
        or None
    )
    if enabled and _provider_needs_api_key(fallback_provider) and not fallback_api_key:
        raise RuntimeError(
            "Для облачного AI_TEXT_FALLBACK_PROVIDER задайте "
            "AI_TEXT_FALLBACK_API_KEY, BYESU_API_KEY или OPENAI_API_KEY."
        )

    return _TextSettings(
        enabled=enabled,
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=parse_bounded_integer(
            os.getenv("AI_TEXT_TIMEOUT_SECONDS", "180"),
            variable_name="AI_TEXT_TIMEOUT_SECONDS",
            default=180,
            minimum=10,
            maximum=900,
        ),
        max_attempts=parse_bounded_integer(
            os.getenv("AI_TEXT_MAX_ATTEMPTS", "2"),
            variable_name="AI_TEXT_MAX_ATTEMPTS",
            default=2,
            minimum=1,
            maximum=5,
        ),
        max_output_tokens=parse_bounded_integer(
            os.getenv("AI_TEXT_MAX_OUTPUT_TOKENS", "1800"),
            variable_name="AI_TEXT_MAX_OUTPUT_TOKENS",
            default=1800,
            minimum=128,
            maximum=16000,
        ),
        max_history_messages=parse_bounded_integer(
            os.getenv("AI_TEXT_MAX_HISTORY_MESSAGES", "30"),
            variable_name="AI_TEXT_MAX_HISTORY_MESSAGES",
            default=30,
            minimum=6,
            maximum=120,
        ),
        fallback_provider=fallback_provider,
        fallback_base_url=fallback_base_url,
        fallback_model=fallback_model,
        fallback_api_key=fallback_api_key,
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
    allowed_user_ids = parse_allowed_user_ids(os.getenv("ALLOWED_USER_IDS", ""))
    allowed_usernames = parse_allowed_usernames(os.getenv("ALLOWED_USERNAMES", ""))
    if not allowed_user_ids and not allowed_usernames:
        raise RuntimeError(
            "Не задан владелец бота. Укажите ALLOWED_USER_IDS или "
            "ALLOWED_USERNAMES в .env."
        )

    shared_cloud_key = _shared_cloud_api_key()
    vision = _load_vision_settings(shared_cloud_key)
    text = _load_text_settings(shared_cloud_key)

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        allowed_user_ids=allowed_user_ids,
        allowed_usernames=allowed_usernames,
        log_chat_id=parse_optional_chat_id(os.getenv("LOG_CHAT_ID", "")),
        analytics_channel_ids=parse_integer_list(
            os.getenv("ANALYTICS_CHANNEL_IDS", ""),
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
        ai_vision_enabled=vision.enabled,
        ai_vision_provider=vision.provider,
        ai_vision_base_url=vision.base_url,
        ai_vision_model=vision.model,
        ai_vision_compare_model=vision.compare_model,
        ai_vision_fallback_model=vision.fallback_model,
        ai_vision_api_key=vision.api_key,
        ai_vision_timeout_seconds=vision.timeout_seconds,
        ai_vision_max_attempts=vision.max_attempts,
        ai_text_enabled=text.enabled,
        ai_text_provider=text.provider,
        ai_text_base_url=text.base_url,
        ai_text_model=text.model,
        ai_text_api_key=text.api_key,
        ai_text_timeout_seconds=text.timeout_seconds,
        ai_text_max_attempts=text.max_attempts,
        ai_text_max_output_tokens=text.max_output_tokens,
        ai_text_max_history_messages=text.max_history_messages,
        ai_text_fallback_provider=text.fallback_provider,
        ai_text_fallback_base_url=text.fallback_base_url,
        ai_text_fallback_model=text.fallback_model,
        ai_text_fallback_api_key=text.fallback_api_key,
        moderator_user_ids=parse_integer_list(
            os.getenv("MODERATOR_USER_IDS", ""),
            variable_name="MODERATOR_USER_IDS",
        ),
        adult_channel_id=parse_chat_id(
            os.getenv("ADULT_CHANNEL_ID", str(DEFAULT_ADULT_CHANNEL_ID)),
            variable_name="ADULT_CHANNEL_ID",
            default=DEFAULT_ADULT_CHANNEL_ID,
        ),
    )


__all__ = (
    "DEFAULT_ADULT_CHANNEL_ID",
    "LOCAL_OPENAI_COMPATIBLE_PROVIDER",
    "Settings",
    "load_settings",
    "parse_allowed_user_ids",
    "parse_allowed_usernames",
    "parse_boolean",
    "parse_bounded_integer",
    "parse_chat_id",
    "parse_integer_list",
    "parse_optional_chat_id",
    "parse_required_path",
    "parse_timezone",
    "validate_local_vision_base_url",
)
