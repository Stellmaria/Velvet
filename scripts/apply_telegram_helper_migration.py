from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SHARED_EDIT_IMPORT = (
    "from velvet_bot.presentation.telegram.shared import safe_edit_message_text\n"
)
SHARED_CALLBACK_EDIT_IMPORT = (
    "from velvet_bot.presentation.telegram.shared import safe_edit_callback_text\n"
)
SHARED_DOWNLOAD_IMPORT = (
    "from velvet_bot.presentation.telegram.shared import download_telegram_file\n"
)

STANDARD_SAFE_EDIT_BODY = '''    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise'''

SHARED_SAFE_EDIT_BODY = '''    await safe_edit_message_text(
        message,
        text,
        reply_markup=keyboard,
        bad_request_type=TelegramBadRequest,
    )'''

SYSTEM_SAFE_EDIT = '''async def _safe_edit(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Системное меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise'''

SYSTEM_SHARED_SAFE_EDIT = '''async def _safe_edit(
    callback: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    await safe_edit_callback_text(
        callback,
        text,
        reply_markup=keyboard,
        unavailable_text="Системное меню больше недоступно.",
        bad_request_type=TelegramBadRequest,
    )'''

IMAGE_DOWNLOAD = '''async def _download_image(bot: Bot, file_id: str) -> bytes:
    errors: list[BaseException] = []
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            destination = io.BytesIO()
            await bot.download(
                file_id,
                destination=destination,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                seek=True,
            )
            value = destination.getvalue()
            if value:
                return value
            errors.append(RuntimeError("Telegram вернул пустой файл."))
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest as error:
            errors.append(error)
            break
        except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
            errors.append(error)
            if attempt >= _DOWNLOAD_ATTEMPTS:
                break
            await asyncio.sleep(_RETRY_DELAYS[attempt - 1])
        except TelegramAPIError as error:
            errors.append(error)
            break
    if errors:
        raise RuntimeError(f"Не удалось скачать изображение: {errors[-1]}")
    raise RuntimeError("Telegram вернул пустой файл.")'''

IMAGE_SHARED_DOWNLOAD = '''async def download_image(bot: Bot, file_id: str) -> bytes:
    return await download_telegram_file(
        bot,
        file_id,
        attempts=_DOWNLOAD_ATTEMPTS,
        timeout_seconds=_DOWNLOAD_TIMEOUT_SECONDS,
        retry_delays=_RETRY_DELAYS,
        failure_label="изображение",
        bad_request_type=TelegramBadRequest,
        network_error_types=(
            TelegramNetworkError,
            TimeoutError,
            ConnectionError,
            OSError,
        ),
        api_error_type=TelegramAPIError,
    )


_download_image = download_image'''

REFERENCE_DOWNLOAD = IMAGE_DOWNLOAD.replace("_download_image", "_download_file")
REFERENCE_SHARED_DOWNLOAD = IMAGE_SHARED_DOWNLOAD.replace(
    "download_image", "download_reference_file"
).replace("_download_image", "_download_file")


def _path(value: str) -> Path:
    return ROOT / value


def _add_import(source: str, import_line: str) -> str:
    if import_line.strip() in source:
        return source
    marker = "from __future__ import annotations\n\n"
    if marker not in source:
        raise RuntimeError("future import marker is missing")
    return source.replace(marker, marker + import_line + "\n", 1)


def _replace(path_value: str, old: str, new: str, *, required: bool = True) -> bool:
    path = _path(path_value)
    source = path.read_text(encoding="utf-8")
    if old not in source:
        if new in source:
            return False
        if required:
            raise RuntimeError(f"expected migration fragment is missing in {path_value}")
        return False
    path.write_text(source.replace(old, new), encoding="utf-8")
    return True


def _migrate_standard_safe_edits() -> list[str]:
    changed: list[str] = []
    for path in sorted((ROOT / "velvet_bot").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if STANDARD_SAFE_EDIT_BODY not in source:
            continue
        source = source.replace(STANDARD_SAFE_EDIT_BODY, SHARED_SAFE_EDIT_BODY)
        source = _add_import(source, SHARED_EDIT_IMPORT)
        path.write_text(source, encoding="utf-8")
        changed.append(path.relative_to(ROOT).as_posix())
    return changed


def _migrate_system_safe_edit() -> list[str]:
    path_value = "velvet_bot/presentation/telegram/routers/system.py"
    path = _path(path_value)
    source = path.read_text(encoding="utf-8")
    if SYSTEM_SAFE_EDIT not in source:
        if SYSTEM_SHARED_SAFE_EDIT in source:
            return []
        raise RuntimeError("system safe edit contract changed unexpectedly")
    source = source.replace(SYSTEM_SAFE_EDIT, SYSTEM_SHARED_SAFE_EDIT)
    source = _add_import(source, SHARED_CALLBACK_EDIT_IMPORT)
    path.write_text(source, encoding="utf-8")
    return [path_value]


def _migrate_public_controller_contracts() -> list[str]:
    changed: list[str] = []

    aliases = (
        (
            "velvet_bot/presentation/telegram/routers/analytics_controllers/management_common.py",
            "\ndef _character_detail(item: CharacterPickerItem) -> str:\n",
            "\nbuild_management_pager = _pager\n\n\ndef _character_detail(item: CharacterPickerItem) -> str:\n",
        ),
        (
            "velvet_bot/presentation/telegram/routers/analytics_controllers/dashboard.py",
            "\ndef _main_text(period: str) -> str:\n",
            "\nbuild_analytics_page_keyboard = _page_keyboard\n\n\ndef _main_text(period: str) -> str:\n",
        ),
        (
            "velvet_bot/presentation/telegram/routers/publication/center.py",
            "\ndef _center_keyboard() -> InlineKeyboardMarkup:\n",
            "\nsafe_edit_publication_message = _safe_edit\n\n\ndef _center_keyboard() -> InlineKeyboardMarkup:\n",
        ),
    )
    for path_value, old, new in aliases:
        if _replace(path_value, old, new):
            changed.append(path_value)

    replacements = (
        (
            "velvet_bot/presentation/telegram/routers/analytics_controllers/management_publications.py",
            "    _pager,\n",
            "    build_management_pager as _pager,\n",
        ),
        (
            "velvet_bot/presentation/telegram/routers/analytics_controllers/management_tags.py",
            "    _pager,\n",
            "    build_management_pager as _pager,\n",
        ),
        (
            "velvet_bot/presentation/telegram/routers/workspace_analytics_characters.py",
            "    _page_keyboard,\n",
            "    build_analytics_page_keyboard as _page_keyboard,\n",
        ),
        (
            "velvet_bot/presentation/telegram/routers/workspace_publications.py",
            "    _safe_edit,\n",
            "    safe_edit_publication_message as _safe_edit,\n",
        ),
        (
            "velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_pose.py",
            "    _download_image,\n",
            "    download_image as _download_image,\n",
        ),
        (
            "velvet_bot/presentation/telegram/routers/workspace_reference_library.py",
            "    _download_file,\n",
            "    download_reference_file as _download_file,\n",
        ),
    )
    for path_value, old, new in replacements:
        if _replace(path_value, old, new):
            changed.append(path_value)
    return changed


def _migrate_downloads() -> list[str]:
    changed: list[str] = []
    targets = (
        (
            "velvet_bot/presentation/telegram/routers/quality_operations_controllers/velvet_ai_image_prompt.py",
            IMAGE_DOWNLOAD,
            IMAGE_SHARED_DOWNLOAD,
        ),
        (
            "velvet_bot/presentation/telegram/routers/references/comparison.py",
            REFERENCE_DOWNLOAD,
            REFERENCE_SHARED_DOWNLOAD,
        ),
    )
    for path_value, old, new in targets:
        path = _path(path_value)
        source = path.read_text(encoding="utf-8")
        if old in source:
            source = source.replace(old, new)
            source = _add_import(source, SHARED_DOWNLOAD_IMPORT)
            path.write_text(source, encoding="utf-8")
            changed.append(path_value)
        elif new not in source:
            raise RuntimeError(f"download migration fragment is missing in {path_value}")
    return changed


def _refresh_navigation_inventory() -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/telegram_navigation_inventory.py",
            "--root",
            "velvet_bot",
            "--markdown",
            "docs/generated/telegram_navigation_inventory.md",
        ],
        cwd=ROOT,
        check=True,
    )


def main() -> int:
    changed = []
    changed.extend(_migrate_standard_safe_edits())
    changed.extend(_migrate_system_safe_edit())
    changed.extend(_migrate_downloads())
    changed.extend(_migrate_public_controller_contracts())
    _refresh_navigation_inventory()
    subprocess.run(
        [sys.executable, "scripts/inventory_telegram_helpers.py", "--check"],
        cwd=ROOT,
        check=True,
    )
    if changed:
        print("Migrated Telegram helper consumers:")
        for path in sorted(set(changed)):
            print(f"- {path}")
    else:
        print("Telegram helper migration is already applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
