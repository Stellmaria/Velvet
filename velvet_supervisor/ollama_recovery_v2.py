from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from velvet_supervisor import ollama_recovery as core

_HOST = os.getenv("VELVET_OLLAMA_HOST", "127.0.0.1:11435").strip() or "127.0.0.1:11435"
_BASE_URL = f"http://{_HOST}"
_DEFAULT_STORAGE = Path.home() / ".ollama" / "models"


def _configure_core() -> None:
    core._BASE_URL = _BASE_URL
    core._ENV_VALUES["AI_VISION_BASE_URL"] = _BASE_URL
    core._ENV_VALUES["AI_TEXT_BASE_URL"] = _BASE_URL


def _project_dir() -> Path:
    return Path.cwd().resolve()


def _write_windows_user_value(name: str, value: str) -> None:
    if os.name != "nt":
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _broadcast_environment_change() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            3000,
            ctypes.byref(result),
        )
    except (AttributeError, OSError):
        return


def _selected_storage() -> Path:
    selected = core.choose_e_storage()
    if selected is not None:
        return selected.path
    target = Path(r"E:\OllamaModels")
    target.joinpath("blobs").mkdir(parents=True, exist_ok=True)
    target.joinpath("manifests").mkdir(parents=True, exist_ok=True)
    return target


def _remove_empty_parents(path: Path, *, stop: Path) -> None:
    current = path
    while current != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _merge_blob(source: Path, destination: Path) -> tuple[int, int, int]:
    """Return moved files, removed duplicates and bytes freed on source drive."""

    source_size = source.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.move(str(source), str(destination))
        return 1, 0, source_size

    destination_size = destination.stat().st_size
    if source.name.endswith("-partial"):
        if source_size > destination_size:
            destination.unlink()
            shutil.move(str(source), str(destination))
            return 1, 0, source_size
        source.unlink()
        return 0, 1, source_size

    if source_size == destination_size:
        source.unlink()
        return 0, 1, source_size

    print(
        "ВНИМАНИЕ: blob с одинаковым именем имеет разный размер, "
        f"оставлен на C: {source}",
        flush=True,
    )
    return 0, 0, 0


def merge_default_storage_into_e(target: Path) -> dict[str, int]:
    source = _DEFAULT_STORAGE
    result = {
        "moved_blobs": 0,
        "duplicate_blobs": 0,
        "moved_manifests": 0,
        "duplicate_manifests": 0,
        "freed_bytes": 0,
    }
    if source.resolve() == target.resolve() or not source.exists():
        return result

    source_blobs = source / "blobs"
    target_blobs = target / "blobs"
    if source_blobs.is_dir():
        target_blobs.mkdir(parents=True, exist_ok=True)
        for item in tuple(source_blobs.iterdir()):
            if not item.is_file():
                continue
            moved, duplicate, freed = _merge_blob(item, target_blobs / item.name)
            result["moved_blobs"] += moved
            result["duplicate_blobs"] += duplicate
            result["freed_bytes"] += freed

    source_manifests = source / "manifests"
    target_manifests = target / "manifests"
    if source_manifests.is_dir():
        for item in tuple(source_manifests.rglob("*")):
            if not item.is_file():
                continue
            relative = item.relative_to(source_manifests)
            destination = target_manifests / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.move(str(item), str(destination))
                result["moved_manifests"] += 1
                continue
            try:
                same = item.read_bytes() == destination.read_bytes()
            except OSError:
                same = False
            if same:
                item.unlink()
                result["duplicate_manifests"] += 1

    _remove_empty_parents(source_blobs, stop=source) if source_blobs.exists() else None
    if source_manifests.exists():
        for directory in sorted(
            (item for item in source_manifests.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            source_manifests.rmdir()
        except OSError:
            pass
    try:
        source.rmdir()
    except OSError:
        pass
    return result


def stop_all_ollama() -> None:
    if os.name != "nt":
        return
    for image in ("ollama.exe", "ollama app.exe"):
        try:
            subprocess.run(
                ["taskkill.exe", "/F", "/T", "/IM", image],
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
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not core._api_is_ready():
            return
        time.sleep(0.5)


def _runtime_environment(storage: Path) -> dict[str, str]:
    environment = os.environ.copy()
    core._apply_runtime_environment(environment)
    environment["OLLAMA_HOST"] = _HOST
    environment["OLLAMA_MODELS"] = str(storage)
    return environment


def start_dedicated_ollama(project_dir: Path, storage: Path) -> None:
    if core._api_is_ready():
        print(f"Velvet Ollama уже доступен на {_BASE_URL}.", flush=True)
        return
    executable = shutil.which("ollama")
    if not executable:
        raise core.OllamaRecoveryError("ollama.exe не найден в PATH Supervisor.")

    logs_dir = project_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "ollama-velvet-11435.log"
    kwargs: dict[str, Any] = {
        "cwd": str(project_dir),
        "env": _runtime_environment(storage),
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        kwargs["start_new_session"] = True

    with log_path.open("a", encoding="utf-8") as stream:
        kwargs["stdout"] = stream
        kwargs["stderr"] = subprocess.STDOUT
        subprocess.Popen([executable, "serve"], **kwargs)

    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        if core._api_is_ready():
            print(
                f"Velvet Ollama запущен на {_BASE_URL}; storage={storage}; log={log_path}",
                flush=True,
            )
            return
        time.sleep(1.0)
    raise core.OllamaRecoveryError(
        f"Velvet Ollama не открыл {_BASE_URL} за 45 секунд. Проверьте {log_path}."
    )


def configure_runtime(project_dir: Path, storage: Path) -> Path:
    core.configure_ollama_storage_env(project_dir, storage)
    core._write_windows_user_environment(storage)
    core._write_env_values(
        project_dir / ".env",
        {
            **core._ENV_VALUES,
            "OLLAMA_MODELS": str(storage),
            "OLLAMA_HOST": _HOST,
        },
    )
    _write_windows_user_value("OLLAMA_HOST", _HOST)
    os.environ["OLLAMA_MODELS"] = str(storage)
    os.environ["OLLAMA_HOST"] = _HOST
    _broadcast_environment_change()
    return project_dir / ".env"


def prepare_runtime(project_dir: Path) -> Path:
    storage = _selected_storage()
    print(f"Целевое хранилище Velvet Ollama: {storage}", flush=True)
    stop_all_ollama()
    migration = merge_default_storage_into_e(storage)
    print(
        "Перенос C: → E: "
        f"blobs moved={migration['moved_blobs']}, "
        f"duplicates removed={migration['duplicate_blobs']}, "
        f"manifests moved={migration['moved_manifests']}, "
        f"freed={migration['freed_bytes'] / (1024 ** 3):.2f} GB",
        flush=True,
    )
    env_path = configure_runtime(project_dir, storage)
    print(f"Обновлён {env_path}; API={_BASE_URL}", flush=True)
    start_dedicated_ollama(project_dir, storage)
    return storage


def print_list() -> None:
    names = core._api_model_names()
    print("NAME")
    for name in names:
        print(name)


def print_status(project_dir: Path) -> None:
    print(f"Velvet Ollama API: {_BASE_URL}")
    print(f"Default Ollama storage: {_DEFAULT_STORAGE}")
    core.print_status(project_dir)


def repair(project_dir: Path) -> None:
    print("Шаг 1/6: остановка Ollama и перенос моделей с C: на E:", flush=True)
    storage = prepare_runtime(project_dir)
    print("Шаг 2/6: конфигурация vision/text маршрутов", flush=True)
    configure_runtime(project_dir, storage)
    print("Шаг 3/6: проверка выделенного Velvet Ollama", flush=True)
    start_dedicated_ollama(project_dir, storage)
    print("Шаг 4/6: поиск моделей в API и manifests", flush=True)
    disk_models = core.scan_manifest_models(storage)
    print("Найдено в manifests: " + (", ".join(disk_models) or "нет"), flush=True)
    print("Шаг 5/6: установка отсутствующих моделей", flush=True)
    pulled = core.ensure_model_bundle(project_dir, storage)
    print(
        "Загружено/перерегистрировано: " + (", ".join(pulled) if pulled else "ничего"),
        flush=True,
    )
    print("Шаг 6/6: проверка capabilities всего набора", flush=True)
    core.verify_model_bundle()
    print(
        "Набор Ollama готов. Выполните самоперезапуск Supervisor и бота, "
        "чтобы они перечитали API 11435 и маршруты моделей.",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    _configure_core()
    parser = argparse.ArgumentParser(description="Dedicated Ollama runtime for Velvet")
    parser.add_argument(
        "action",
        choices=("status", "configure", "start", "pull", "show", "repair", "list"),
    )
    args = parser.parse_args(argv)
    project_dir = _project_dir()
    try:
        if args.action == "status":
            print_status(project_dir)
        elif args.action == "configure":
            storage = _selected_storage()
            env_path = configure_runtime(project_dir, storage)
            print(f"Обновлён {env_path}. Требуется самоперезапуск Supervisor.")
        elif args.action == "start":
            storage = prepare_runtime(project_dir)
            start_dedicated_ollama(project_dir, storage)
        elif args.action == "pull":
            storage = prepare_runtime(project_dir)
            core.ensure_model_bundle(project_dir, storage)
        elif args.action == "show":
            core.verify_model_bundle()
        elif args.action == "list":
            print_list()
        else:
            repair(project_dir)
    except core.OllamaRecoveryError as error:
        print(f"ОШИБКА: {error}", flush=True)
        return 1
    except OSError as error:
        print(f"ОШИБКА ФАЙЛОВОЙ СИСТЕМЫ: {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "configure_runtime",
    "merge_default_storage_into_e",
    "prepare_runtime",
    "start_dedicated_ollama",
    "stop_all_ollama",
)
