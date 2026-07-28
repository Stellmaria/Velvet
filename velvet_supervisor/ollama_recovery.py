from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_MODEL = "qwen3-vl:4b"
_BASE_URL = "http://127.0.0.1:11434"
_ENV_VALUES = {
    "AI_VISION_ENABLED": "true",
    "AI_VISION_PROVIDER": "ollama",
    "AI_VISION_BASE_URL": _BASE_URL,
    "AI_VISION_MODEL": _MODEL,
    "AI_VISION_COMPARE_MODEL": "",
    "AI_VISION_TIMEOUT_SECONDS": "600",
}
_ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


class OllamaRecoveryError(RuntimeError):
    pass


def _project_dir() -> Path:
    return Path.cwd().resolve()


def _request_json(
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    data = None
    headers: dict[str, str] = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        f"{_BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise OllamaRecoveryError(f"Ollama API недоступен: {error}") from error
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OllamaRecoveryError("Ollama вернул некорректный JSON.") from error
    if not isinstance(decoded, dict):
        raise OllamaRecoveryError("Ollama вернул неожиданный формат ответа.")
    return decoded


def _api_is_ready() -> bool:
    try:
        _request_json("/api/tags", timeout=2.5)
    except OllamaRecoveryError:
        return False
    return True


def _read_env_values(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    raw = env_path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _ENV_LINE_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        if key not in _ENV_VALUES or key in values:
            continue
        values[key] = line.split("=", 1)[1].strip()
    return values


def configure_vision_env(project_dir: Path) -> Path:
    env_path = project_dir / ".env"
    raw = env_path.read_bytes() if env_path.exists() else b""
    has_bom = raw.startswith(codecs.BOM_UTF8)
    text = raw.decode("utf-8-sig", errors="strict") if raw else ""
    newline = "\r\n" if b"\r\n" in raw else "\n"

    output: list[str] = []
    written: set[str] = set()
    for line in text.splitlines():
        match = _ENV_LINE_RE.match(line)
        key = match.group(1) if match else None
        if key not in _ENV_VALUES:
            output.append(line)
            continue
        if key in written:
            continue
        output.append(f"{key}={_ENV_VALUES[key]}")
        written.add(key)

    missing = [key for key in _ENV_VALUES if key not in written]
    if missing and output and output[-1].strip():
        output.append("")
    output.extend(f"{key}={_ENV_VALUES[key]}" for key in missing)

    updated = newline.join(output).rstrip("\r\n") + newline
    encoded = (codecs.BOM_UTF8 if has_bom else b"") + updated.encode("utf-8")
    env_path.parent.mkdir(parents=True, exist_ok=True)

    previous_mode = env_path.stat().st_mode if env_path.exists() else None
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=env_path.parent,
        prefix=".env.ollama-",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(encoded)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    if previous_mode is not None:
        os.chmod(temporary_path, previous_mode)
    os.replace(temporary_path, env_path)
    return env_path


def start_ollama(project_dir: Path) -> None:
    if _api_is_ready():
        print("Ollama API уже доступен.", flush=True)
        return

    executable = shutil.which("ollama")
    if not executable:
        raise OllamaRecoveryError("ollama.exe не найден в PATH Supervisor.")

    logs_dir = project_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "ollama-supervisor.log"
    environment = os.environ.copy()
    environment["OLLAMA_HOST"] = _BASE_URL

    popen_kwargs: dict[str, Any] = {
        "cwd": str(project_dir),
        "env": environment,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        popen_kwargs["start_new_session"] = True

    with log_path.open("a", encoding="utf-8") as log_stream:
        popen_kwargs["stdout"] = log_stream
        popen_kwargs["stderr"] = subprocess.STDOUT
        subprocess.Popen([executable, "serve"], **popen_kwargs)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if _api_is_ready():
            print(f"Ollama запущен. Лог: {log_path}", flush=True)
            return
        time.sleep(1.0)
    raise OllamaRecoveryError(
        f"Ollama не открыл {_BASE_URL} за 30 секунд. Проверьте {log_path}."
    )


def pull_model(project_dir: Path) -> None:
    executable = shutil.which("ollama")
    if not executable:
        raise OllamaRecoveryError("ollama.exe не найден в PATH Supervisor.")
    environment = os.environ.copy()
    environment["OLLAMA_HOST"] = _BASE_URL
    print(f"Загрузка модели {_MODEL}...", flush=True)
    completed = subprocess.run(
        [executable, "pull", _MODEL],
        cwd=str(project_dir),
        env=environment,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode:
        raise OllamaRecoveryError(
            f"ollama pull {_MODEL} завершился с кодом {completed.returncode}."
        )


def verify_model() -> tuple[str, ...]:
    payload = _request_json("/api/show", payload={"model": _MODEL}, timeout=30.0)
    raw_capabilities = payload.get("capabilities")
    capabilities = tuple(
        str(item).strip().casefold()
        for item in raw_capabilities
        if str(item).strip()
    ) if isinstance(raw_capabilities, list) else ()
    if "vision" not in capabilities:
        shown = ", ".join(capabilities) or "не указаны"
        raise OllamaRecoveryError(
            f"Модель {_MODEL} установлена, но capability vision отсутствует: {shown}."
        )
    return capabilities


def print_status(project_dir: Path) -> None:
    env_path = project_dir / ".env"
    values = _read_env_values(env_path)
    print(f"Проект: {project_dir}")
    print(f"Файл конфигурации: {env_path}")
    for key in _ENV_VALUES:
        print(f"{key}={values.get(key, '<не задано>')}")
    try:
        tags = _request_json("/api/tags", timeout=3.0)
    except OllamaRecoveryError as error:
        print(f"Ollama API: недоступен ({error})")
        return
    names: list[str] = []
    raw_models = tags.get("models")
    if isinstance(raw_models, list):
        for item in raw_models:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
    print("Ollama API: доступен")
    print("Модели: " + (", ".join(names) if names else "нет"))


def repair(project_dir: Path) -> None:
    print("Шаг 1/4: безопасная настройка AI vision", flush=True)
    env_path = configure_vision_env(project_dir)
    print(f"Обновлён {env_path}: только {', '.join(_ENV_VALUES)}", flush=True)

    print("Шаг 2/4: запуск Ollama", flush=True)
    start_ollama(project_dir)

    print(f"Шаг 3/4: установка {_MODEL}", flush=True)
    pull_model(project_dir)

    print("Шаг 4/4: проверка vision capability", flush=True)
    capabilities = verify_model()
    print(f"Модель {_MODEL} готова. Capabilities: {', '.join(capabilities)}", flush=True)
    print(
        "Теперь выполните самоперезапуск Supervisor, чтобы он перечитал обновлённый .env.",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe Ollama recovery for Velvet Supervisor")
    parser.add_argument(
        "action",
        choices=("status", "configure", "start", "pull", "show", "repair"),
    )
    args = parser.parse_args(argv)
    project_dir = _project_dir()
    try:
        if args.action == "status":
            print_status(project_dir)
        elif args.action == "configure":
            env_path = configure_vision_env(project_dir)
            print(f"Обновлён {env_path}. Требуется самоперезапуск Supervisor.")
        elif args.action == "start":
            start_ollama(project_dir)
        elif args.action == "pull":
            start_ollama(project_dir)
            pull_model(project_dir)
        elif args.action == "show":
            capabilities = verify_model()
            print(f"{_MODEL}: {', '.join(capabilities)}")
        else:
            repair(project_dir)
    except OllamaRecoveryError as error:
        print(f"ОШИБКА: {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
