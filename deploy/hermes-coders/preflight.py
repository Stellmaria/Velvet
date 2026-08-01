from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from ensure_runtime_config import config_has_env_passthrough


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


def require_readable_file(path: Path) -> str:
    try:
        if not path.is_file():
            raise PreflightError(f"Отсутствует Hermes-файл: {path}")
        return path.read_text(encoding="utf-8")
    except PermissionError as exc:
        raise PreflightError(
            f"Нет доступа к Hermes-файлу {path}; проверьте владельца, группу и режим"
        ) from exc


def validate_data(path: Path) -> None:
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


def validate_api_key(path: Path, values: dict[str, str]) -> str:
    key = values.get("API_SERVER_KEY", "")
    if len(key) < 24:
        raise PreflightError(
            f"API_SERVER_KEY в {path} должен содержать минимум 24 символа"
        )
    return key


def main() -> int:
    velvet_env_path = ROOT / "secrets" / "velvet.env"
    max_env_path = ROOT / "secrets" / "max.env"
    velvet_env = require_private_file(velvet_env_path)
    max_env = require_private_file(max_env_path)

    required = (
        "BYESU_HERMES_CODEX_API_KEY",
        "BYESU_HERMES_GPT_PRO_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_USERS",
        "GH_TOKEN",
        "API_SERVER_KEY",
    )
    require_values(velvet_env_path, velvet_env, required)
    require_values(max_env_path, max_env, required)

    if velvet_env["TELEGRAM_BOT_TOKEN"] == max_env["TELEGRAM_BOT_TOKEN"]:
        raise PreflightError("Два coder-контейнера не могут использовать один Telegram bot token")
    if velvet_env["GH_TOKEN"] == max_env["GH_TOKEN"]:
        raise PreflightError("Velvet и Max должны использовать разные fine-grained GitHub tokens")

    velvet_api_key = validate_api_key(velvet_env_path, velvet_env)
    max_api_key = validate_api_key(max_env_path, max_env)
    if velvet_api_key == max_api_key:
        raise PreflightError("Velvet и Max должны использовать разные API_SERVER_KEY")

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

    validate_workspace(ROOT / "workspaces" / "velvet")
    validate_workspace(ROOT / "workspaces" / "max")
    validate_data(ROOT / "data" / "velvet")
    validate_data(ROOT / "data" / "max")

    print("Hermes Coder preflight: OK")
    print("- workspaces: isolated")
    print("- Telegram tokens: distinct")
    print("- GitHub tokens: distinct")
    print("- API server keys: distinct")
    print("- PostgreSQL identities: read-only")
    print("- model routing: mini -> terra -> luna")
    print("- terminal passthrough: GH_TOKEN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreflightError as exc:
        print(f"Hermes Coder preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
