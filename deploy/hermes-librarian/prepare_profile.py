from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


DISABLED_TOOLSETS = (
    "browser",
    "clarify",
    "code_execution",
    "cronjob",
    "debugging",
    "delegation",
    "discord",
    "discord_admin",
    "feishu_doc",
    "feishu_drive",
    "file",
    "homeassistant",
    "image_gen",
    "kanban",
    "memory",
    "messaging",
    "moa",
    "rl",
    "safe",
    "search",
    "session_search",
    "skills",
    "spotify",
    "terminal",
    "todo",
    "tts",
    "video",
    "vision",
    "web",
    "yuanbao",
)
DEFAULT_LOCAL_MODEL = "velvet-librarian-local:v1"
DEFAULT_LOCAL_BASE_URL = "http://ollama-librarian:11434/v1"
DEFAULT_LOCAL_CONTEXT_LENGTH = 65536


class ProfileError(RuntimeError):
    pass


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _local_context_length() -> int:
    raw = os.getenv(
        "STORAGE_LIBRARIAN_LOCAL_CONTEXT_LENGTH",
        str(DEFAULT_LOCAL_CONTEXT_LENGTH),
    ).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ProfileError(
            "STORAGE_LIBRARIAN_LOCAL_CONTEXT_LENGTH должен быть целым числом."
        ) from error
    if not 65536 <= value <= 262144:
        raise ProfileError(
            "STORAGE_LIBRARIAN_LOCAL_CONTEXT_LENGTH должен быть от 65536 до 262144."
        )
    return value


def prepare(
    source_config: Path,
    target_dir: Path,
    soul_source: Path,
    agents_source: Path,
) -> None:
    if not source_config.is_file():
        raise ProfileError(f"Отсутствует исходный Hermes config: {source_config}")
    if not soul_source.is_file() or not agents_source.is_file():
        raise ProfileError("Отсутствует SOUL.md или AGENTS.md Velvet Librarian.")

    decoded = yaml.safe_load(source_config.read_text(encoding="utf-8"))
    config = _mapping(decoded)

    # API server is the only platform for this profile. An explicit empty
    # platform whitelist is combined with a global deny-list so plugin or
    # future default toolsets cannot silently grant capabilities.
    config["platform_toolsets"] = {"api_server": []}
    agent = _mapping(config.get("agent"))
    agent["disabled_toolsets"] = list(DISABLED_TOOLSETS)
    config["agent"] = agent

    local_model = (
        os.getenv("STORAGE_LIBRARIAN_LOCAL_MODEL", DEFAULT_LOCAL_MODEL).strip()
        or DEFAULT_LOCAL_MODEL
    )
    local_base_url = (
        os.getenv(
            "STORAGE_LIBRARIAN_LOCAL_BASE_URL",
            DEFAULT_LOCAL_BASE_URL,
        ).strip().rstrip("/")
        or DEFAULT_LOCAL_BASE_URL
    )

    # Librarian uses only the private Ollama endpoint. Cloud fallbacks and
    # inherited auxiliary cloud routes are deliberately removed so a local
    # failure cannot silently spend tokens.
    config["model"] = {
        "default": local_model,
        "provider": "custom",
        "base_url": local_base_url,
        "context_length": _local_context_length(),
    }
    config["fallback_providers"] = []
    config.pop("fallback_model", None)
    config["auxiliary"] = {
        "title_generation": {"enabled": False},
        "compression": {
            "provider": "main",
            "model": local_model,
        },
    }
    compression = _mapping(config.get("compression"))
    for key in ("provider", "model", "base_url", "api_key"):
        compression.pop(key, None)
    config["compression"] = compression

    # Librarian never needs project checkout, terminal hooks, MCP or browser.
    terminal = _mapping(config.get("terminal"))
    terminal["cwd"] = "/opt/data"
    terminal.pop("env_passthrough", None)
    config["terminal"] = terminal
    config["mcp_servers"] = {}
    config["hooks"] = []
    config["worktree"] = False

    target_dir.mkdir(parents=True, exist_ok=True)
    target_config = target_dir / "config.yaml"
    target_config.write_text(
        yaml.safe_dump(
            config,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    shutil.copyfile(soul_source, target_dir / "SOUL.md")
    shutil.copyfile(agents_source, target_dir / "AGENTS.md")

    for path in (
        target_config,
        target_dir / "SOUL.md",
        target_dir / "AGENTS.md",
    ):
        os.chmod(path, 0o640)


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        raise ProfileError(
            "usage: prepare_profile.py SOURCE_CONFIG TARGET_DIR SOUL_SOURCE AGENTS_SOURCE"
        )
    prepare(*(Path(item) for item in argv[1:]))
    print("Velvet Librarian profile prepared with local Ollama and all toolsets disabled.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (ProfileError, OSError, yaml.YAMLError) as error:
        print(f"Velvet Librarian profile preparation failed: {error}", file=sys.stderr)
        raise SystemExit(2)
