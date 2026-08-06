#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

_ALLOWED_PROJECTS = frozenset({"velvet", "max"})
_ALLOWED_POLICIES = frozenset({"read_only", "workspace_write"})
_ROUTE_MODELS = {
    "codex_subscription": frozenset({"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"}),
    "byesu_provider": frozenset({"gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.6-terra"}),
}
_COMMON_HOME_FILES = ("AGENTS.md", "output.schema.json", "context-manifest.json")
_SUBSCRIPTION_HOME_FILES = ("auth.json", "config.toml")
_SANDBOX_MODE = re.compile(r'(?m)^sandbox_mode\s*=\s*"workspace-write"\s*$')
_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
_IMAGE_REQUEST_PATH = Path("/workspace/.git/hermes-image-request.json")


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required sandbox environment: {name}")
    return value


def copy_regular_file(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise RuntimeError(f"required Codex home file is invalid: {source.name}")
    shutil.copyfile(source, target)
    target.chmod(0o600)


def prepare_codex_home(source: Path, target: Path, *, route: str) -> None:
    if source.is_symlink() or not source.is_dir():
        raise RuntimeError("read-only Codex home is missing or unsafe")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in _COMMON_HOME_FILES:
        copy_regular_file(source / name, target / name)
    if route == "codex_subscription":
        for name in _SUBSCRIPTION_HOME_FILES:
            copy_regular_file(source / name, target / name)
        config_path = target / "config.toml"
        config = config_path.read_text(encoding="utf-8")
        config, count = _SANDBOX_MODE.subn(
            'sandbox_mode = "danger-full-access"',
            config,
            count=1,
        )
        if count != 1:
            raise RuntimeError("subscription config does not declare workspace-write once")
        config_path.write_text(config, encoding="utf-8")
        config_path.chmod(0o600)


def provider_config(model: str) -> str:
    env_key = "BYESU_HERMES_CODEX_API_KEY"
    return f'''model = "{model}"
model_provider = "byesu"
model_reasoning_effort = "high"
sandbox_mode = "danger-full-access"
approval_policy = "never"
check_for_update_on_startup = false

[model_providers.byesu]
name = "Byesu"
base_url = "https://byesu.com/v1"
env_key = "{env_key}"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 2
stream_max_retries = 2
stream_idle_timeout_ms = 300000

[shell_environment_policy]
ignore_default_excludes = true
exclude = [
  "API_SERVER_KEY",
  "BYESU_HERMES_CODEX_API_KEY",
  "CODEX_RUNNER_API_KEY",
  "DATABASE_URL",
  "PGPASSWORD",
  "TELEGRAM_BOT_TOKEN",
]

[features]
apps = false
plugins = false
tool_suggest = false
'''


def configure_git(home: Path, project: str) -> None:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
    }
    identity = {
        "velvet": (
            "Hermes Velvet Coder",
            "hermes-velvet@users.noreply.github.com",
        ),
        "max": (
            "Hermes Max Coder",
            "hermes-max@users.noreply.github.com",
        ),
    }[project]
    commands = (
        ["git", "config", "--global", "user.name", identity[0]],
        ["git", "config", "--global", "user.email", identity[1]],
        ["git", "config", "--global", "--add", "safe.directory", "/workspace"],
        [
            "git",
            "config",
            "--global",
            "credential.https://github.com.helper",
            "!gh auth git-credential",
        ],
    )
    for command in commands:
        result = subprocess.run(
            command,
            check=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError("failed to configure ephemeral Git identity boundary")
    (home / ".gitconfig").chmod(0o600)


def load_image_request() -> dict[str, str] | None:
    if not _IMAGE_REQUEST_PATH.exists():
        return None
    if _IMAGE_REQUEST_PATH.is_symlink() or not _IMAGE_REQUEST_PATH.is_file():
        raise RuntimeError("GPT Image 2 control file is unsafe")
    try:
        payload = json.loads(_IMAGE_REQUEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("GPT Image 2 control file is invalid") from error
    if not isinstance(payload, dict) or set(payload) != {
        "task_kind",
        "reasoning_effort",
    }:
        raise RuntimeError("GPT Image 2 control schema is invalid")
    if payload.get("task_kind") != "image":
        raise RuntimeError("GPT Image 2 task kind is invalid")
    effort = str(payload.get("reasoning_effort") or "")
    if effort not in _REASONING_EFFORTS:
        raise RuntimeError("GPT Image 2 reasoning effort is invalid")
    return {"task_kind": "image", "reasoning_effort": effort}


def execution_env(
    home: Path,
    route: str,
    model: str,
    *,
    image_run: bool,
) -> dict[str, str]:
    allowed = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "CODEX_HOME": str(home),
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "TERM": os.environ.get("TERM", "dumb"),
        "NO_COLOR": "1",
    }
    # Image runs do not need repository credentials. Keep the image tool boundary
    # independent from GitHub even though it reuses the same isolated checkout.
    if not image_run:
        allowed["GH_TOKEN"] = required_env("GH_TOKEN")
    if route == "byesu_provider":
        key_name = "BYESU_HERMES_CODEX_API_KEY"
        allowed[key_name] = required_env(key_name)
    return allowed


def main() -> int:
    project = required_env("HERMES_SANDBOX_PROJECT")
    model = required_env("HERMES_SANDBOX_MODEL")
    route = required_env("HERMES_SANDBOX_ROUTE")
    policy = required_env("HERMES_SANDBOX_MUTATION_POLICY")
    if project not in _ALLOWED_PROJECTS:
        raise RuntimeError("sandbox project is not allowlisted")
    if route not in _ROUTE_MODELS or model not in _ROUTE_MODELS[route]:
        raise RuntimeError("sandbox route/model combination is not allowlisted")
    if policy not in _ALLOWED_POLICIES:
        raise RuntimeError("sandbox mutation policy is not allowlisted")

    source = Path("/opt/codex-ro")
    home = Path("/opt/codex")
    prepare_codex_home(source, home, route=route)
    schema = home / "output.schema.json"
    if route == "byesu_provider":
        config_path = home / "config.toml"
        config_path.write_text(provider_config(model), encoding="utf-8")
        config_path.chmod(0o600)
    configure_git(home, project)
    image_request = load_image_request()

    command = [
        "codex",
        "exec",
        "--json",
        "--model",
        model,
        "--sandbox",
        "danger-full-access",
    ]
    if image_request is not None:
        command.extend(
            [
                "-c",
                f'model_reasoning_effort="{image_request["reasoning_effort"]}"',
            ]
        )
    else:
        command.extend(["--output-schema", str(schema)])
    command.append("-")
    os.chdir("/workspace")
    os.execvpe(
        command[0],
        command,
        execution_env(
            home,
            route,
            model,
            image_run=image_request is not None,
        ),
    )
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
