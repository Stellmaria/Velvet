from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hermes-brain"))

from ensure_runtime_config import (  # noqa: E402
    config_has_env_passthrough,
    config_has_mapping_scalar,
)
from verify_installed_context import (  # noqa: E402
    RuntimeContextError,
    verify_installed,
)


ROOT = Path(os.environ.get("HERMES_CODERS_ROOT", "/srv/hermes-coders"))
PRODUCTION_WORKSPACES = {
    Path("/srv/velvet").resolve(),
    Path("/srv/romatic-club").resolve(),
}


class PreflightError(RuntimeError):
    pass


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def require_private_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise PreflightError(f"Отсутствует secret-файл: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PreflightError(
            f"Слишком широкие права на {path}: {mode:04o}; требуется 0600"
        )
    return parse_env(path)


def require_values(path: Path, values: dict[str, str], names: tuple[str, ...]) -> None:
    missing = [name for name in names if not values.get(name)]
    if missing:
        raise PreflightError(
            f"В {path} не заполнены обязательные переменные: {', '.join(missing)}"
        )


def db_identity(values: dict[str, str]) -> tuple[str, str, str]:
    url = values.get("DATABASE_URL", "")
    if url:
        parsed = urlparse(url)
        return (
            unquote(parsed.username or ""),
            parsed.hostname or "",
            (parsed.path or "").lstrip("/"),
        )
    return (
        values.get("PGUSER", ""),
        values.get("PGHOST", ""),
        values.get("PGDATABASE", ""),
    )


def validate_db_env(
    path: Path,
    *,
    expected_user: str,
    expected_database: str,
) -> None:
    values = require_private_file(path)
    user, host, database = db_identity(values)
    if (user, host, database) != (expected_user, "postgres", expected_database):
        raise PreflightError(
            f"Неверная read-only DB identity в {path}: "
            f"ожидалось user={expected_user}, host=postgres, db={expected_database}"
        )


def validate_workspace(path: Path) -> None:
    resolved = path.resolve()
    if resolved in PRODUCTION_WORKSPACES:
        raise PreflightError(f"Coder workspace совпадает с production checkout: {path}")
    if not (path / ".git").is_dir():
        raise PreflightError(f"Workspace не является отдельным Git checkout: {path}")


def validate_codex_workspace(path: Path) -> None:
    validate_workspace(path)
    config = require_readable_file(path / ".git" / "config")
    if "gh auth git-credential" not in config:
        raise PreflightError(f"В {path} не настроен GitHub credential helper")
    if "[user]" not in config or "noreply.github.com" not in config:
        raise PreflightError(f"В {path} не настроена Git identity")


def require_readable_file(path: Path) -> str:
    try:
        if not path.is_file():
            raise PreflightError(f"Отсутствует Hermes-файл: {path}")
        return path.read_text(encoding="utf-8")
    except PermissionError as exc:
        raise PreflightError(
            f"Нет доступа к Hermes-файлу {path}; проверьте владельца, группу и режим"
        ) from exc


def validate_data(path: Path, *, entity: str) -> None:
    config = path / "config.yaml"
    soul = path / "SOUL.md"
    config_text = require_readable_file(config)
    require_readable_file(soul)
    if "api_key:" in config_text:
        raise PreflightError(f"В {config} найден встроенный API key")
    for model in ("gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna"):
        if model not in config_text:
            raise PreflightError(f"В {config} отсутствует модель {model}")
    if "/workspace" not in config_text:
        raise PreflightError(f"В {config} не зафиксирован terminal.cwd=/workspace")
    if not config_has_env_passthrough(config_text, "GH_TOKEN"):
        raise PreflightError(
            f"В {config} не разрешён terminal.env_passthrough для GH_TOKEN"
        )
    for section, key, value in (
        ("terminal", "cwd", "/workspace"),
        ("compression", "enabled", "true"),
        ("tool_loop_guardrails", "warnings_enabled", "true"),
        ("tool_loop_guardrails", "hard_stop_enabled", "true"),
    ):
        if not config_has_mapping_scalar(config_text, section, key, value):
            raise PreflightError(f"В {config} отсутствует {section}.{key}={value}")
    try:
        verify_installed(path, entity=entity, mode="hermes")
    except RuntimeContextError as error:
        raise PreflightError(str(error)) from error


def validate_api_key(path: Path, values: dict[str, str], name: str) -> str:
    key = values.get(name, "")
    if len(key) < 24:
        raise PreflightError(f"{name} в {path} должен содержать минимум 24 символа")
    return key


def validate_codex_home(path: Path, *, entity: str) -> None:
    if not path.is_dir():
        raise PreflightError(f"Отсутствует CODEX_HOME: {path}")
    config = path / "config.toml"
    auth = path / "auth.json"
    config_text = require_readable_file(config)
    if 'model = "gpt-5.6-terra"' not in config_text:
        raise PreflightError(f"В {config} не задан безопасный default gpt-5.6-terra")
    required_config = (
        'sandbox_mode = "workspace-write"',
        'approval_policy = "never"',
        'cli_auth_credentials_store = "file"',
        'check_for_update_on_startup = false',
        'network_access = true',
        'ignore_default_excludes = true',
        'apps = false',
        'plugins = false',
        'tool_suggest = false',
    )
    missing_config = [item for item in required_config if item not in config_text]
    if missing_config:
        raise PreflightError(
            f"В {config} отсутствуют обязательные Codex настройки: "
            + ", ".join(missing_config)
        )
    for secret in (
        "API_SERVER_KEY",
        "BYESU_HERMES_CODEX_API_KEY",
        "BYESU_HERMES_MEDIA_API_KEY",
        "CODEX_RUNNER_API_KEY",
        "DATABASE_URL",
        "PGPASSWORD",
        "TELEGRAM_BOT_TOKEN",
    ):
        if f'"{secret}"' not in config_text:
            raise PreflightError(f"В {config} shell policy не исключает {secret}")
    if '"GH_TOKEN"' in config_text:
        raise PreflightError(f"В {config} GH_TOKEN ошибочно исключён из Codex shell")
    if not auth.is_file() or auth.stat().st_size == 0:
        raise PreflightError(
            f"Codex не авторизован в {path}; выполните codex-login.sh для проекта"
        )
    mode = stat.S_IMODE(auth.stat().st_mode)
    if mode & 0o077:
        raise PreflightError(f"Слишком широкие права на {auth}: {mode:04o}; требуется 0600")
    try:
        verify_installed(path, entity=entity, mode="codex")
    except RuntimeContextError as error:
        raise PreflightError(str(error)) from error


def main() -> int:
    velvet_env_path = ROOT / "secrets" / "velvet.env"
    max_env_path = ROOT / "secrets" / "max.env"
    velvet_env = require_private_file(velvet_env_path)
    max_env = require_private_file(max_env_path)

    required = (
        "BYESU_HERMES_CODEX_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USERS",
        "GH_TOKEN",
        "API_SERVER_KEY",
        "CODEX_RUNNER_API_KEY",
    )
    require_values(velvet_env_path, velvet_env, required)
    require_values(max_env_path, max_env, required)

    media_key = velvet_env.get("BYESU_HERMES_MEDIA_API_KEY", "")
    if media_key:
        validate_api_key(
            velvet_env_path,
            velvet_env,
            "BYESU_HERMES_MEDIA_API_KEY",
        )
    if max_env.get("BYESU_HERMES_MEDIA_API_KEY", ""):
        raise PreflightError(
            "Max не должен получать BYESU_HERMES_MEDIA_API_KEY: image route принадлежит Velvet"
        )

    if velvet_env["TELEGRAM_BOT_TOKEN"] == max_env["TELEGRAM_BOT_TOKEN"]:
        raise PreflightError("Два coder-контейнера не могут использовать один Telegram bot token")
    if velvet_env["GH_TOKEN"] == max_env["GH_TOKEN"]:
        raise PreflightError("Velvet и Max должны использовать разные fine-grained GitHub tokens")

    velvet_api_key = validate_api_key(velvet_env_path, velvet_env, "API_SERVER_KEY")
    max_api_key = validate_api_key(max_env_path, max_env, "API_SERVER_KEY")
    if velvet_api_key == max_api_key:
        raise PreflightError("Velvet и Max должны использовать разные API_SERVER_KEY")

    velvet_runner_key = validate_api_key(
        velvet_env_path, velvet_env, "CODEX_RUNNER_API_KEY"
    )
    max_runner_key = validate_api_key(max_env_path, max_env, "CODEX_RUNNER_API_KEY")
    if velvet_runner_key == max_runner_key:
        raise PreflightError("Velvet и Max должны использовать разные CODEX_RUNNER_API_KEY")
    if velvet_runner_key != velvet_api_key or max_runner_key != max_api_key:
        raise PreflightError(
            "CODEX_RUNNER_API_KEY должен совпадать с API_SERVER_KEY своего проекта, "
            "пока router использует существующий Runs API token contract"
        )

    validate_db_env(
        ROOT / "secrets" / "velvet-db.env",
        expected_user="hermes_velvet_ro",
        expected_database="velvet",
    )
    validate_db_env(
        ROOT / "secrets" / "max-db.env",
        expected_user="hermes_max_ro",
        expected_database="card_hunter",
    )

    for workspace in (
        ROOT / "workspaces" / "velvet",
        ROOT / "workspaces" / "max",
    ):
        validate_workspace(workspace)
    validate_codex_workspace(ROOT / "workspaces" / "velvet-codex")
    validate_codex_workspace(ROOT / "workspaces" / "max-codex")
    validate_data(ROOT / "data" / "velvet", entity="velvet-coder")
    validate_data(ROOT / "data" / "max", entity="max-coder")
    validate_codex_home(ROOT / "codex" / "velvet", entity="velvet-coder")
    validate_codex_home(ROOT / "codex" / "max", entity="max-coder")

    print("Hermes Coder preflight: OK")
    print("- Hermes chat gateways: isolated")
    print("- Codex workspaces and auth: isolated")
    print("- Telegram tokens: distinct")
    print("- GitHub tokens: distinct")
    print("- Runs API keys: distinct")
    print("- PostgreSQL identities: read-only")
    print("- Codex routing: luna -> terra -> sol")
    print("- Byesu media credential: Velvet-only when configured")
    print("- Codex CLI minimum: 0.144.0; image pin: 0.144.1")
    print("- Codex sandbox: workspace-write + GitHub network")
    print("- Velvet Brain manifests and context hashes: verified")
    print("- terminal passthrough: GH_TOKEN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreflightError as exc:
        print(f"Hermes Coder preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
