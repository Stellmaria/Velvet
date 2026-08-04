from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import unquote, urlsplit


_PLACEHOLDER_MARKERS = (
    "replace_with",
    "insert_",
    "change_me",
    "changeme",
    "your_",
    "example",
    "placeholder",
)
_SECRET_NAMES = {
    "BOT_TOKEN",
    "POSTGRES_PASSWORD",
    "STORAGE_ENCRYPTION_SECRET",
    "STORAGE_ENCRYPTION_KEYRING",
    "SUPERVISOR_TOKEN",
    "BYESU_API_KEY",
    "AI_TEXT_API_KEY",
    "AI_TEXT_FALLBACK_API_KEY",
    "AI_VISION_API_KEY",
    "AI_VISION_FLASH_API_KEY",
    "AI_VISION_PRO_API_KEY",
    "AI_VISION_SENSITIVE_API_KEY",
    "KIE_API_KEY",
    "GRS_API_KEY",
    "HERMES_API_KEY",
    "KRITA_REMOTE_WORKER_TOKEN",
    "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "GH_TOKEN",
    "API_SERVER_KEY",
}
_LOCAL_VISION_PROVIDER = "local_openai_compatible"
_LOCAL_VISION_HOSTS = frozenset({"vision-gateway"})
_VISION_PROVIDERS = frozenset(
    {"openai_compatible", _LOCAL_VISION_PROVIDER, "ollama"}
)


@dataclass(slots=True)
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def passed(self, message: str) -> None:
        self.checks.append(message)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def validate_server_environment(
    values: dict[str, str],
    *,
    env_path: Path | None = None,
    hermes_values: dict[str, str] | None = None,
    check_permissions: bool = True,
) -> ValidationReport:
    report = ValidationReport()
    _validate_required_base(values, report)
    _validate_database(values, report)
    _validate_telegram(values, report)
    _validate_storage(values, report)
    _validate_safety_flags(values, report)
    _validate_krita_remote(values, report)
    _validate_text_ai(values, report)
    _validate_vision_ai(values, report)
    _validate_kie(values, report)
    _validate_hermes(values, hermes_values, report)
    _validate_codex(values, report)
    _validate_data_directory(values, report)
    if env_path is not None and check_permissions:
        _validate_env_permissions(env_path, report)
    return report


def _validate_required_base(values: dict[str, str], report: ValidationReport) -> None:
    required = (
        "BOT_TOKEN",
        "DATABASE_URL",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "ALLOWED_USER_IDS",
        "STORAGE_ENCRYPTION_SECRET",
        "STORAGE_ENCRYPTION_ACTIVE_KEY_ID",
        "SUPERVISOR_TOKEN",
        "VELVET_DATA_DIR",
    )
    missing = [name for name in required if not _configured(values.get(name, ""))]
    if missing:
        report.error("Не настроены обязательные переменные: " + ", ".join(missing))
    else:
        report.passed("Обязательные server-переменные заполнены без placeholders.")

    for name in (
        "POSTGRES_PASSWORD",
        "STORAGE_ENCRYPTION_SECRET",
        "SUPERVISOR_TOKEN",
    ):
        value = values.get(name, "")
        if _configured(value) and len(value) < 24:
            report.error(f"{name} должен содержать не менее 24 символов.")


def _validate_database(values: dict[str, str], report: ValidationReport) -> None:
    raw_url = values.get("DATABASE_URL", "").strip()
    if not raw_url:
        return
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        report.error("DATABASE_URL должен использовать postgresql:// или postgres://.")
        return
    if parsed.hostname != "postgres":
        report.error(
            "DATABASE_URL в server Compose должен обращаться к сервису postgres, "
            "а не к localhost или внешнему адресу."
        )
    expected_user = values.get("POSTGRES_USER", "")
    expected_db = values.get("POSTGRES_DB", "")
    expected_password = values.get("POSTGRES_PASSWORD", "")
    actual_db = parsed.path.lstrip("/")
    if expected_user and unquote(parsed.username or "") != expected_user:
        report.error("Пользователь DATABASE_URL не совпадает с POSTGRES_USER.")
    if expected_db and actual_db != expected_db:
        report.error("Имя базы DATABASE_URL не совпадает с POSTGRES_DB.")
    if expected_password and unquote(parsed.password or "") != expected_password:
        report.error("Пароль DATABASE_URL не совпадает с POSTGRES_PASSWORD.")
    if parsed.port not in {None, 5432}:
        report.warn("DATABASE_URL использует нестандартный порт PostgreSQL.")
    if not report.errors:
        report.passed("DATABASE_URL согласован с внутренним сервисом PostgreSQL.")


def _validate_telegram(values: dict[str, str], report: ValidationReport) -> None:
    token = values.get("BOT_TOKEN", "")
    if _configured(token) and not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}", token):
        report.error("BOT_TOKEN не похож на Telegram bot token.")
    owner_ids = _csv(values.get("ALLOWED_USER_IDS", ""))
    if not owner_ids or any(not item.isdigit() or int(item) <= 0 for item in owner_ids):
        report.error("ALLOWED_USER_IDS должен содержать положительные числовые Telegram ID.")
    for name in (
        "LOG_CHAT_ID",
        "ADULT_CHANNEL_ID",
        "TELEGRAM_STORAGE_CHAT_ID",
        "WATERMARK_STORAGE_CHAT_ID",
    ):
        value = values.get(name, "").strip()
        if value and not re.fullmatch(r"-?\d+", value):
            report.error(f"{name} должен быть числовым Telegram chat ID.")


def _validate_storage(values: dict[str, str], report: ValidationReport) -> None:
    active_key_id = values.get("STORAGE_ENCRYPTION_ACTIVE_KEY_ID", "").strip()
    active_secret = values.get("STORAGE_ENCRYPTION_SECRET", "").strip()
    legacy_key_id = values.get("STORAGE_ENCRYPTION_LEGACY_KEY_ID", "").strip()
    key_id_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    if active_key_id and not key_id_pattern.fullmatch(active_key_id):
        report.error(
            "STORAGE_ENCRYPTION_ACTIVE_KEY_ID должен содержать 1–64 безопасных символа."
        )

    configured_keys: dict[str, str] = {}
    raw_keyring = values.get("STORAGE_ENCRYPTION_KEYRING", "").strip()
    if raw_keyring:
        try:
            payload = json.loads(raw_keyring)
        except json.JSONDecodeError:
            report.error("STORAGE_ENCRYPTION_KEYRING должен быть JSON-объектом key_id:secret.")
            payload = {}
        if not isinstance(payload, dict):
            report.error("STORAGE_ENCRYPTION_KEYRING должен быть JSON-объектом key_id:secret.")
        else:
            for key_id, secret in payload.items():
                if not isinstance(key_id, str) or not isinstance(secret, str):
                    report.error(
                        "STORAGE_ENCRYPTION_KEYRING принимает только строковые key ID и secrets."
                    )
                    continue
                if not key_id_pattern.fullmatch(key_id):
                    report.error(f"Некорректный backup key ID: {key_id!r}.")
                if len(secret) < 24:
                    report.error(
                        f"Historical backup key {key_id!r} должен содержать не менее 24 символов."
                    )
                configured_keys[key_id] = secret

    if active_key_id:
        configured_keys[active_key_id] = active_secret
    if legacy_key_id and legacy_key_id not in configured_keys:
        report.error(
            "STORAGE_ENCRYPTION_LEGACY_KEY_ID должен присутствовать в active/historical keyring."
        )
    auth_secrets = {
        values.get("BOT_TOKEN", "").strip(),
        values.get("SUPERVISOR_TOKEN", "").strip(),
    } - {""}
    reused = sorted(
        key_id for key_id, secret in configured_keys.items() if secret in auth_secrets
    )
    if reused:
        report.error(
            "Backup encryption keys не должны совпадать с BOT_TOKEN или SUPERVISOR_TOKEN: "
            + ", ".join(reused)
        )
    if active_key_id and active_secret and not reused:
        report.passed(
            "Backup keyring настроен отдельно от authentication tokens; "
            f"active={active_key_id}, keys={len(configured_keys)}."
        )

    storage_chat = values.get("TELEGRAM_STORAGE_CHAT_ID", "").strip()
    thread_names = (
        "STORAGE_THREAD_WATERMARKS",
        "STORAGE_THREAD_BACKUPS",
        "STORAGE_THREAD_DIAGNOSTICS",
        "STORAGE_THREAD_EXPORTS",
        "STORAGE_THREAD_CODEX",
        "STORAGE_THREAD_RELEASES",
        "STORAGE_THREAD_REWORK",
    )
    configured_threads = [name for name in thread_names if values.get(name, "").strip()]
    if configured_threads and not storage_chat:
        report.error("Storage thread IDs заданы без TELEGRAM_STORAGE_CHAT_ID.")
    for name in configured_threads:
        if not values[name].isdigit() or int(values[name]) <= 0:
            report.error(f"{name} должен быть положительным message_thread_id.")
    if _flag(values, "STORAGE_MIGRATE_ON_START"):
        report.warn(
            "STORAGE_MIGRATE_ON_START=true: после первичного переноса переключите в false."
        )


def _validate_safety_flags(values: dict[str, str], report: ValidationReport) -> None:
    if _flag(values, "SUPERVISOR_ALLOW_REMOTE"):
        report.error("SUPERVISOR_ALLOW_REMOTE должен оставаться false на production VPS.")
    if _flag(values, "KRITA_WATERMARK_ENABLED"):
        report.error("KRITA_WATERMARK_ENABLED должен быть false на Linux VPS без bridge.")
    if _flag(values, "AI_VISION_QUEUE_ENABLED") and not _flag(
        values, "AI_VISION_ENABLED"
    ):
        report.error("AI_VISION_QUEUE_ENABLED требует AI_VISION_ENABLED=true.")
    if not _flag(values, "AI_BUDGET_ENABLED", default=True):
        report.error("AI_BUDGET_ENABLED нельзя выключать при production-переносе.")
    for name in (
        "AI_DAILY_BUDGET_RUB",
        "AI_MONTHLY_BUDGET_RUB",
        "AI_MAX_REQUEST_RUB",
        "AI_HERMES_RESERVE_RUB",
    ):
        if _decimal(values.get(name, "")) is None:
            report.error(f"{name} должен быть неотрицательным числом.")


def _krita_bind_is_loopback(host: str) -> bool:
    normalized = host.strip().strip("[]")
    if normalized.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validate_krita_remote(values: dict[str, str], report: ValidationReport) -> None:
    enabled = _flag(values, "KRITA_REMOTE_WORKER_ENABLED")
    host = values.get("KRITA_REMOTE_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1"
    unsafe = _flag(values, "KRITA_REMOTE_ALLOW_UNSAFE_PUBLIC_BIND")
    token = values.get("KRITA_REMOTE_WORKER_TOKEN", "").strip()
    if enabled and (not _configured(token) or len(token) < 32):
        report.error(
            "KRITA_REMOTE_WORKER_ENABLED требует отдельный "
            "KRITA_REMOTE_WORKER_TOKEN длиной не менее 32 символов."
        )
    if _krita_bind_is_loopback(host):
        if enabled:
            report.passed("Krita Remote API ограничен loopback bind.")
    elif not unsafe:
        report.error(
            "KRITA_REMOTE_BIND_HOST должен быть loopback. Публичный/wildcard bind "
            "требует явный KRITA_REMOTE_ALLOW_UNSAFE_PUBLIC_BIND=true и внешний "
            "защищённый gateway."
        )
    else:
        report.warn(
            "Krita Remote API использует явный unsafe bind; проверьте loopback host "
            "publish, private VPN либо mTLS gateway."
        )


def _validate_text_ai(values: dict[str, str], report: ValidationReport) -> None:
    if not _flag(values, "AI_TEXT_ENABLED"):
        return
    _require_configured(
        values,
        report,
        ("AI_TEXT_PROVIDER", "AI_TEXT_BASE_URL", "AI_TEXT_MODEL"),
        context="включённого RP-контура",
    )
    provider = values.get("AI_TEXT_PROVIDER", "").strip().casefold()
    if provider == "ollama":
        report.error(
            "AI_TEXT_PROVIDER=ollama запрещён на production VPS: Ollama legacy/deprecated."
        )
    if not _api_key(values, "AI_TEXT_API_KEY"):
        report.error("AI_TEXT_ENABLED требует AI_TEXT_API_KEY или BYESU_API_KEY.")
    if not _has_positive_pricing(values, "AI_TEXT"):
        report.error("AI_TEXT_ENABLED требует положительную input/output цену.")
    if values.get("AI_TEXT_FALLBACK_MODEL", "").strip():
        _require_configured(
            values,
            report,
            ("AI_TEXT_FALLBACK_PROVIDER", "AI_TEXT_FALLBACK_BASE_URL"),
            context="RP fallback",
        )
        fallback_provider = values.get("AI_TEXT_FALLBACK_PROVIDER", "").strip().casefold()
        if fallback_provider == "ollama":
            report.error(
                "AI_TEXT_FALLBACK_PROVIDER=ollama запрещён: Ollama legacy/deprecated."
            )
        if not _api_key(values, "AI_TEXT_FALLBACK_API_KEY"):
            report.error("RP fallback требует отдельный API key или BYESU_API_KEY.")
        if not _has_positive_pricing(values, "AI_TEXT_FALLBACK"):
            report.error("RP fallback требует положительную input/output цену.")


def _validate_vision_ai(values: dict[str, str], report: ValidationReport) -> None:
    if not _flag(values, "AI_VISION_ENABLED"):
        return
    _require_configured(
        values,
        report,
        ("AI_VISION_PROVIDER", "AI_VISION_BASE_URL", "AI_VISION_MODEL"),
        context="включённого VL-контура",
    )
    base_provider = values.get("AI_VISION_PROVIDER", "").strip().casefold()
    base_url = values.get("AI_VISION_BASE_URL", "").strip()
    if base_provider not in _VISION_PROVIDERS:
        report.error(
            "AI_VISION_PROVIDER должен быть openai_compatible или "
            "local_openai_compatible."
        )
    if base_provider == "ollama":
        report.error(
            "AI_VISION_PROVIDER=ollama запрещён на production VPS: Ollama legacy/deprecated."
        )
    elif base_provider == _LOCAL_VISION_PROVIDER:
        _validate_local_vision_endpoint(
            base_url,
            report,
            variable_name="AI_VISION_BASE_URL",
        )
    elif not _api_key(values, "AI_VISION_API_KEY"):
        report.error("AI_VISION_ENABLED требует AI_VISION_API_KEY или BYESU_API_KEY.")

    flash_model = values.get("AI_VISION_FLASH_MODEL", "").strip() or values.get(
        "AI_VISION_MODEL", ""
    ).strip()
    if not flash_model:
        report.error("VL cascade требует Flash model ID.")
    _validate_vision_route(
        values,
        report,
        route="FLASH",
        inherited_provider=base_provider,
        inherited_base_url=base_url,
    )

    for route, legacy_name in (
        ("PRO", "AI_VISION_COMPARE_MODEL"),
        ("SENSITIVE", "AI_VISION_FALLBACK_MODEL"),
    ):
        model = values.get(f"AI_VISION_{route}_MODEL", "").strip() or values.get(
            legacy_name, ""
        ).strip()
        if model:
            _validate_vision_route(
                values,
                report,
                route=route,
                inherited_provider=base_provider,
                inherited_base_url=base_url,
            )


def _validate_vision_route(
    values: dict[str, str],
    report: ValidationReport,
    *,
    route: str,
    inherited_provider: str,
    inherited_base_url: str,
) -> None:
    prefix = f"AI_VISION_{route}"
    explicit_provider = values.get(f"{prefix}_PROVIDER", "").strip().casefold()
    explicit_base_url = values.get(f"{prefix}_BASE_URL", "").strip()
    provider = explicit_provider or inherited_provider
    base_url = explicit_base_url or inherited_base_url

    if provider not in _VISION_PROVIDERS:
        report.error(
            f"{route} VL route использует неподдерживаемый provider: {provider or '<empty>'}."
        )
        return
    if provider == "ollama":
        report.error(f"{route} VL route не может использовать legacy/deprecated Ollama.")
        return
    if explicit_provider and explicit_provider != inherited_provider and not explicit_base_url:
        report.error(
            f"{route} VL route при смене provider требует отдельный {prefix}_BASE_URL."
        )

    if provider == _LOCAL_VISION_PROVIDER:
        _validate_local_vision_endpoint(
            base_url,
            report,
            variable_name=f"{prefix}_BASE_URL",
        )
        if not _has_zero_or_empty_pricing(values, prefix):
            report.error(
                f"{route} local VL route должна иметь нулевую monetary pricing."
            )
        return

    if not _api_key(values, f"{prefix}_API_KEY"):
        report.error(f"{route} VL route требует API key или BYESU_API_KEY.")
    if not _has_positive_pricing(values, prefix):
        report.error(f"{route} VL route требует положительную input/output цену.")


def _validate_local_vision_endpoint(
    base_url: str,
    report: ValidationReport,
    *,
    variable_name: str,
) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"}:
        report.error(
            f"{variable_name} для local VL должен использовать http:// или https://."
        )
        return
    if parsed.username or parsed.password:
        report.error(f"{variable_name} для local VL не может содержать credentials.")
    if parsed.hostname not in _LOCAL_VISION_HOSTS:
        allowed = ", ".join(sorted(_LOCAL_VISION_HOSTS))
        report.error(
            f"{variable_name} для local VL должен использовать внутренний "
            f"Compose host: {allowed}."
        )
    if parsed.query or parsed.fragment:
        report.error(
            f"{variable_name} для local VL не может содержать query или fragment."
        )


def _validate_kie(values: dict[str, str], report: ValidationReport) -> None:
    if not _flag(values, "KIE_ENABLED"):
        return
    _require_configured(
        values,
        report,
        (
            "KIE_API_KEY",
            "KIE_BASE_URL",
            "KIE_FILE_UPLOAD_BASE_URL",
            "GRS_API_KEY",
            "GRS_BASE_URL",
            "KIE_SEEDREAM_5_PRO_TEXT_MODEL",
            "KIE_SEEDREAM_5_PRO_IMAGE_MODEL",
            "KIE_WAN_27_IMAGE_MODEL",
            "KIE_WAN_27_IMAGE_PRO_MODEL",
            "GRS_NANO_BANANA_2_MODEL",
            "GRS_NANO_BANANA_PRO_MODEL",
            "KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL",
            "KIE_GROK_IMAGINE_VIDEO_15_MODEL",
            "KIE_SEEDANCE_15_PRO_MODEL",
            "KIE_WAN_27_IMAGE_TO_VIDEO_MODEL",
        ),
        context="включённого Kie + GRS media-контура",
    )
    rate = _decimal(values.get("KIE_USD_TO_RUB", ""))
    if rate is None or rate <= 0:
        report.error("KIE_ENABLED требует положительный KIE_USD_TO_RUB.")


def _validate_hermes(
    values: dict[str, str],
    hermes_values: dict[str, str] | None,
    report: ValidationReport,
) -> None:
    if not _flag(values, "HERMES_INCIDENT_ENABLED"):
        return
    _require_configured(
        values,
        report,
        ("HERMES_BASE_URL", "HERMES_API_KEY"),
        context="включённого Hermes incident-контура",
    )
    base_url = values.get("HERMES_BASE_URL", "")
    if base_url and urlsplit(base_url).hostname != "hermes":
        report.error("В server Compose HERMES_BASE_URL должен использовать host hermes.")
    if hermes_values is None:
        report.error("HERMES_INCIDENT_ENABLED требует проверки файла .env.hermes.")
        return
    _require_configured(
        hermes_values,
        report,
        (
            "OPENAI_API_KEY",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_ALLOWED_USERS",
            "GH_TOKEN",
            "API_SERVER_KEY",
        ),
        context="Hermes",
    )
    if hermes_values.get("TELEGRAM_BOT_TOKEN") == values.get("BOT_TOKEN"):
        report.error("Velvet и Hermes должны использовать разные Telegram bot tokens.")
    if hermes_values.get("API_SERVER_KEY") != values.get("HERMES_API_KEY"):
        report.error("API_SERVER_KEY в .env.hermes не совпадает с HERMES_API_KEY.")


def _validate_codex(values: dict[str, str], report: ValidationReport) -> None:
    if not _flag(values, "CODEX_ENABLED"):
        return
    _require_configured(
        values,
        report,
        ("CODEX_COMMAND", "CODEX_MODEL", "CODEX_WORKTREE_DIR"),
        context="включённого Codex-контура",
    )
    report.warn(
        "CODEX_ENABLED=true: auth.json/config.toml и отдельный Linux user "
        "проверяются вручную вне bot-контейнера."
    )


def _validate_data_directory(values: dict[str, str], report: ValidationReport) -> None:
    raw = values.get("VELVET_DATA_DIR", "").strip()
    if not raw or _placeholder(raw):
        return
    path = Path(raw)
    if not path.is_absolute():
        report.error("VELVET_DATA_DIR должен быть абсолютным путём на VPS.")
        return
    if path.exists() and not os.access(path, os.W_OK | os.X_OK):
        report.error("VELVET_DATA_DIR существует, но недоступен для записи.")
    elif not path.exists():
        report.warn("VELVET_DATA_DIR ещё не создан; используйте --create-directories.")


def _validate_env_permissions(path: Path, report: ValidationReport) -> None:
    if os.name == "nt" or not path.exists():
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        report.error(f"{path.name} должен иметь права 600, текущие права слишком широкие.")
    else:
        report.passed(f"Права {path.name} не открывают секреты группе или другим пользователям.")


def create_data_directories(values: dict[str, str]) -> list[Path]:
    root = Path(values["VELVET_DATA_DIR"]).expanduser()
    created: list[Path] = []
    for relative in ("postgres", "backups", "logs", "runtime", "hermes", "vision"):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
    return created


def check_host_tools(report: ValidationReport) -> None:
    docker = shutil.which("docker")
    if docker is None:
        report.error("Команда docker не найдена.")
        return
    try:
        result = subprocess.run(
            [docker, "compose", "version"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        report.error("Не удалось выполнить docker compose version.")
        return
    if result.returncode != 0:
        report.error("Docker Compose plugin недоступен.")
    else:
        report.passed("Docker Engine и Compose plugin доступны.")


def _require_configured(
    values: dict[str, str],
    report: ValidationReport,
    names: tuple[str, ...],
    *,
    context: str,
) -> None:
    missing = [name for name in names if not _configured(values.get(name, ""))]
    if missing:
        report.error(f"Для {context} не настроены: " + ", ".join(missing))


def _api_key(values: dict[str, str], specific_name: str) -> bool:
    return _configured(values.get(specific_name, "")) or _configured(
        values.get("BYESU_API_KEY", "")
    )


def _has_positive_pricing(values: dict[str, str], prefix: str) -> bool:
    input_price = _decimal(values.get(f"{prefix}_INPUT_RUB_PER_1M", ""))
    output_price = _decimal(values.get(f"{prefix}_OUTPUT_RUB_PER_1M", ""))
    return bool(
        (input_price is not None and input_price > 0)
        or (output_price is not None and output_price > 0)
    )


def _has_zero_or_empty_pricing(values: dict[str, str], prefix: str) -> bool:
    for suffix in ("INPUT_RUB_PER_1M", "OUTPUT_RUB_PER_1M"):
        raw = values.get(f"{prefix}_{suffix}", "").strip()
        if not raw:
            continue
        parsed = _decimal(raw)
        if parsed is None or parsed != 0:
            return False
    return True


def _configured(value: str) -> bool:
    return bool(value.strip()) and not _placeholder(value)


def _placeholder(value: str) -> bool:
    normalized = value.strip().casefold()
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def _flag(values: dict[str, str], name: str, *, default: bool = False) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on", "да"}


def _decimal(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _print_report(report: ValidationReport) -> None:
    for message in report.checks:
        print(f"[OK] {message}")
    for message in report.warnings:
        print(f"[WARN] {message}")
    for message in report.errors:
        print(f"[ERROR] {message}", file=sys.stderr)
    print(
        f"Server preflight: checks={len(report.checks)} "
        f"warnings={len(report.warnings)} errors={len(report.errors)}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Velvet VPS configuration.")
    parser.add_argument("--env-file", default=".env.server")
    parser.add_argument("--hermes-env", default=".env.hermes")
    parser.add_argument("--skip-host-tools", action="store_true")
    parser.add_argument("--skip-permissions", action="store_true")
    parser.add_argument("--create-directories", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env_path = Path(args.env_file)
    if not env_path.is_file():
        print(f"[ERROR] Server env file not found: {env_path}", file=sys.stderr)
        return 1
    values = parse_env_file(env_path)
    hermes_path = Path(args.hermes_env)
    hermes_values = parse_env_file(hermes_path) if hermes_path.is_file() else None
    if args.create_directories and _configured(values.get("VELVET_DATA_DIR", "")):
        create_data_directories(values)
    report = validate_server_environment(
        values,
        env_path=env_path,
        hermes_values=hermes_values,
        check_permissions=not args.skip_permissions,
    )
    if not args.skip_host_tools:
        check_host_tools(report)
    _print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
