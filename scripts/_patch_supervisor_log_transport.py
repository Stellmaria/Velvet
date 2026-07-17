from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "velvet_supervisor/runtime.py"
ERROR_CENTER = ROOT / "velvet_bot/error_center.py"
# Patch is intentionally guarded by exact source contracts and AST validation.


def replace_once(source: str, old: str, new: str, *, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: ожидалось одно совпадение, найдено {count}")
    return source.replace(old, new, 1)


def patch_runtime() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    source = replace_once(
        source,
        "            env=os.environ.copy(),\n",
        "            env=_child_environment(),\n",
        label="child environment call",
    )
    helper = '''def _child_environment() -> dict[str, str]:
    """Force one encoding contract between the Windows child and Supervisor."""
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def _is_recoverable_polling_disconnect(line: str) -> bool:
    lowered = line.casefold()
    return (
        "aiogram.dispatcher" in lowered
        and "failed to fetch updates" in lowered
        and "telegramnetworkerror" in lowered
        and (
            "serverdisconnectederror" in lowered
            or "server disconnected" in lowered
        )
    )


'''
    source = replace_once(
        source,
        "def _build_child_logger(logs_dir: Path) -> logging.Logger:\n",
        helper + "def _build_child_logger(logs_dir: Path) -> logging.Logger:\n",
        label="runtime helpers",
    )
    source = replace_once(
        source,
        '''def _looks_like_error(line: str) -> bool:
    lowered = line.casefold()
    return any(
''',
        '''def _looks_like_error(line: str) -> bool:
    if _is_recoverable_polling_disconnect(line):
        return False
    lowered = line.casefold()
    return any(
''',
        label="supervisor alert filter",
    )
    ast.parse(source, filename=str(RUNTIME))
    RUNTIME.write_text(source, encoding="utf-8")


def patch_error_center() -> None:
    source = ERROR_CENTER.read_text(encoding="utf-8")
    helper = '''def _is_recoverable_aiogram_polling_record(record: logging.LogRecord) -> bool:
    if record.name != "aiogram.dispatcher":
        return False
    try:
        message = record.getMessage().casefold()
    except Exception:
        message = str(record.msg).casefold()
    return (
        "failed to fetch updates" in message
        and "telegramnetworkerror" in message
        and (
            "serverdisconnectederror" in message
            or "server disconnected" in message
        )
    )


'''
    source = replace_once(
        source,
        "class ErrorLoggingHandler(logging.Handler):\n",
        helper + "class ErrorLoggingHandler(logging.Handler):\n",
        label="incident helper",
    )
    source = replace_once(
        source,
        '''        if record.levelno < logging.WARNING:
            return
        if record.name.startswith(_EXCLUDED_LOGGER_PREFIXES):
''',
        '''        if record.levelno < logging.WARNING:
            return
        if _is_recoverable_aiogram_polling_record(record):
            return
        if record.name.startswith(_EXCLUDED_LOGGER_PREFIXES):
''',
        label="incident filter",
    )
    ast.parse(source, filename=str(ERROR_CENTER))
    ERROR_CENTER.write_text(source, encoding="utf-8")


def main() -> None:
    patch_runtime()
    patch_error_center()


if __name__ == "__main__":
    main()
