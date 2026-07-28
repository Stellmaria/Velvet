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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

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
_E_STORAGE_CANDIDATES = (
    Path(r"E:\OllamaModels"),
    Path(r"E:\OllamaModels\models"),
)


class OllamaRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StorageLayout:
    path: Path
    exists: bool
    has_blobs: bool
    has_manifests: bool
    blob_count: int
    manifest_count: int

    @property
    def valid(self) -> bool:
        return self.has_blobs and self.has_manifests


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


def _count_files(directory: Path, *, recursive: bool) -> int:
    if not directory.is_dir():
        return 0
    try:
        items = directory.rglob("*") if recursive else directory.iterdir()
        return sum(1 for item in items if item.is_file())
    except OSError:
        return 0


def inspect_storage(path: Path) -> StorageLayout:
    blobs = path / "blobs"
    manifests = path / "manifests"
    return StorageLayout(
        path=path,
        exists=path.exists(),
        has_blobs=blobs.is_dir(),
        has_manifests=manifests.is_dir(),
        blob_count=_count_files(blobs, recursive=False),
        manifest_count=_count_files(manifests, recursive=True),
    )


def choose_e_storage(
    candidates: tuple[Path, ...] = _E_STORAGE_CANDIDATES,
) -> StorageLayout | None:
    selected: StorageLayout | None = None
    for candidate in candidates:
        layout = inspect_storage(candidate)
        if not layout.valid:
            continue
        if selected is None or (
            layout.manifest_count,
            layout.blob_count,
        ) > (
            selected.manifest_count,
            selected.blob_count,
        ):
            selected = layout
    return selected


def _read_project_env_value(env_path: Path, key: str) -> str:
    if not env_path.exists():
        return ""
    text = env_path.read_bytes().decode("utf-8-sig", errors="replace")
    for line in text.splitlines():
        match = _ENV_LINE_RE.match(line)
        if match and match.group(1) == key:
            return line.split("=", 1)[1].strip()
    return ""


def _read_env_values(env_path: Path) -> dict[str, str]:
    return {
        key: value
        for key in _ENV_VALUES
        if (value := _read_project_env_value(env_path, key))
        or key == "AI_VISION_COMPARE_MODEL"
    }


def _write_env_values(env_path: Path, values: Mapping[str, str]) -> Path:
    raw = env_path.read_bytes() if env_path.exists() else b""
    has_bom = raw.startswith(codecs.BOM_UTF8)
    text = raw.decode("utf-8-sig", errors="strict") if raw else ""
    newline = "\r\n" if b"\r\n" in raw else "\n"

    output: list[str] = []
    written: set[str] = set()
    for line in text.splitlines():
        match = _ENV_LINE_RE.match(line)
        key = match.group(1) if match else None
        if key not in values:
            output.append(line)
            continue
        if key in written:
            continue
        output.append(f"{key}={values[key]}")
        written.add(key)

    missing = [key for key in values if key not in written]
    if missing and output and output[-1].strip():
        output.append("")
    output.extend(f"{key}={values[key]}" for key in missing)

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


def configure_vision_env(project_dir: Path) -> Path:
    return _write_env_values(project_dir / ".env", _ENV_VALUES)


def configure_ollama_storage_env(project_dir: Path, storage_path: Path) -> Path:
    return _write_env_values(
        project_dir / ".env",
        {"OLLAMA_MODELS": str(storage_path)},
    )


def _read_windows_environment(scope: str) -> str:
    if os.name != "nt":
        return ""
    import winreg

    if scope == "user":
        root = winreg.HKEY_CURRENT_USER
        subkey = "Environment"
    elif scope == "machine":
        root = winreg.HKEY_LOCAL_MACHINE
        subkey = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    else:
        raise ValueError(f"Неизвестная область переменной среды: {scope}")
    try:
        with winreg.OpenKey(root, subkey) as key:
            value, _ = winreg.QueryValueEx(key, "OLLAMA_MODELS")
    except OSError:
        return ""
    return str(value).strip()


def _write_windows_user_environment(storage_path: Path) -> None:
    if os.name != "nt":
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        winreg.SetValueEx(
            key,
            "OLLAMA_MODELS",
            0,
            winreg.REG_SZ,
            str(storage_path),
        )


def _layout_line(layout: StorageLayout) -> str:
    return (
        f"{layout.path}: exists={'да' if layout.exists else 'нет'}; "
        f"blobs={'да' if layout.has_blobs else 'нет'} ({layout.blob_count}); "
        f"manifests={'да' if layout.has_manifests else 'нет'} "
        f"({layout.manifest_count}); valid={'да' if layout.valid else 'нет'}"
    )


def print_storage_status(project_dir: Path) -> StorageLayout | None:
    env_path = project_dir / ".env"
    print("Хранилище Ollama:")
    print(f"  Process OLLAMA_MODELS={os.getenv('OLLAMA_MODELS', '') or '<не задано>'}")
    print(
        "  Project .env OLLAMA_MODELS="
        f"{_read_project_env_value(env_path, 'OLLAMA_MODELS') or '<не задано>'}"
    )
    print(
        "  User OLLAMA_MODELS="
        f"{_read_windows_environment('user') or '<не задано>'}"
    )
    print(
        "  Machine OLLAMA_MODELS="
        f"{_read_windows_environment('machine') or '<не задано>'}"
    )
    layouts = [inspect_storage(path) for path in _E_STORAGE_CANDIDATES]
    for layout in layouts:
        print(f"  {_layout_line(layout)}")
    default_layout = inspect_storage(Path.home() / ".ollama" / "models")
    print(f"  default: {_layout_line(default_layout)}")
    selected = choose_e_storage()
    print(
        "  Рекомендуемый каталог E: "
        + (str(selected.path) if selected is not None else "не найден")
    )
    return selected


def stop_ollama() -> None:
    if not _api_is_ready():
        return
    if os.name != "nt":
        raise OllamaRecoveryError(
            "Автоматический перезапуск Ollama поддерживается только на Windows."
        )
    try:
        completed = subprocess.run(
            ["taskkill.exe", "/F", "/T", "/IM", "ollama.exe"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            shell=False,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise OllamaRecoveryError(f"Не удалось остановить Ollama: {error}") from error

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if not _api_is_ready():
            return
        time.sleep(0.5)
    raise OllamaRecoveryError(
        "Ollama продолжает отвечать после taskkill "
        f"(код {completed.returncode})."
    )


def start_ollama(
    project_dir: Path,
    *,
    storage_path: Path | None = None,
) -> None:
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
    if storage_path is not None:
        environment["OLLAMA_MODELS"] = str(storage_path)

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


def _model_names(tags: dict[str, Any]) -> list[str]:
    names: list[str] = []
    raw_models = tags.get("models")
    if isinstance(raw_models, list):
        for item in raw_models:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
    return names


def prepare_e_storage(project_dir: Path) -> Path | None:
    selected = print_storage_status(project_dir)
    layouts = [inspect_storage(path) for path in _E_STORAGE_CANDIDATES]
    if selected is None:
        if any(layout.exists for layout in layouts):
            raise OllamaRecoveryError(
                "На E: найдены каталоги Ollama, но ни один не содержит одновременно "
                "папки blobs и manifests."
            )
        print(
            "Каталоги E:\\OllamaModels не найдены. "
            "Текущая конфигурация хранилища не изменена.",
            flush=True,
        )
        return None

    configure_ollama_storage_env(project_dir, selected.path)
    _write_windows_user_environment(selected.path)
    os.environ["OLLAMA_MODELS"] = str(selected.path)
    print(
        f"OLLAMA_MODELS закреплён на {selected.path} в project .env и User environment.",
        flush=True,
    )

    if _api_is_ready():
        print("Перезапуск Ollama для применения каталога на E:...", flush=True)
        stop_ollama()
    start_ollama(project_dir, storage_path=selected.path)
    tags = _request_json("/api/tags", timeout=5.0)
    names = _model_names(tags)
    print(
        "Модели после переключения: " + (", ".join(names) if names else "нет"),
        flush=True,
    )
    return selected.path


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
    capabilities = (
        tuple(
            str(item).strip().casefold()
            for item in raw_capabilities
            if str(item).strip()
        )
        if isinstance(raw_capabilities, list)
        else ()
    )
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
    print_storage_status(project_dir)
    try:
        tags = _request_json("/api/tags", timeout=3.0)
    except OllamaRecoveryError as error:
        print(f"Ollama API: недоступен ({error})")
        return
    names = _model_names(tags)
    print("Ollama API: доступен")
    print("Модели: " + (", ".join(names) if names else "нет"))


def repair(project_dir: Path) -> None:
    print("Шаг 1/5: проверка и восстановление хранилища Ollama", flush=True)
    storage_path = prepare_e_storage(project_dir)

    print("Шаг 2/5: безопасная настройка AI vision", flush=True)
    env_path = configure_vision_env(project_dir)
    print(f"Обновлён {env_path}: только {', '.join(_ENV_VALUES)}", flush=True)

    print("Шаг 3/5: запуск Ollama", flush=True)
    start_ollama(project_dir, storage_path=storage_path)

    print(f"Шаг 4/5: установка {_MODEL}", flush=True)
    pull_model(project_dir)

    print("Шаг 5/5: проверка vision capability", flush=True)
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
