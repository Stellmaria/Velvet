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


class ProfileError(RuntimeError):
    pass


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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
    print("Velvet Librarian profile prepared with all toolsets disabled.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (ProfileError, OSError, yaml.YAMLError) as error:
        print(f"Velvet Librarian profile preparation failed: {error}", file=sys.stderr)
        raise SystemExit(2)
