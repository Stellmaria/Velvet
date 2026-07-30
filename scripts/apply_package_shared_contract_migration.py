from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _path(value: str) -> Path:
    return ROOT / value


def _read(value: str) -> str:
    return _path(value).read_text(encoding="utf-8")


def _write(value: str, source: str) -> bool:
    path = _path(value)
    current = path.read_text(encoding="utf-8")
    if current == source:
        return False
    path.write_text(source, encoding="utf-8")
    return True


def _add_import(source: str, import_line: str) -> str:
    if import_line in source:
        return source
    marker = "from __future__ import annotations\n\n"
    if marker not in source:
        raise RuntimeError("future import marker is missing")
    return source.replace(marker, marker + import_line + "\n", 1)


def _append_once(source: str, marker: str, block: str) -> str:
    if marker in source:
        return source
    return source.rstrip() + "\n\n\n" + block.strip() + "\n"


def _replace_regex(
    source: str,
    pattern: str,
    replacement: str,
    *,
    required: bool = True,
    flags: int = 0,
) -> str:
    updated, count = re.subn(pattern, replacement, source, flags=flags)
    if count == 0 and required and replacement not in source:
        raise RuntimeError(f"migration pattern did not match: {pattern[:120]}")
    return updated


def _remove_injected_exception_arguments() -> list[str]:
    changed: list[str] = []
    media_block = re.compile(
        r"\n\s*bad_request_type=TelegramBadRequest,"
        r"\n\s*network_error_types=\("
        r".*?"
        r"\n\s*\),"
        r"\n\s*api_error_type=TelegramAPIError,",
        re.DOTALL,
    )
    for path in sorted((ROOT / "velvet_bot").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        updated = source.replace("\n        bad_request_type=TelegramBadRequest,", "")
        updated = media_block.sub("", updated)
        if updated != source:
            path.write_text(updated, encoding="utf-8")
            changed.append(path.relative_to(ROOT).as_posix())
    return changed


def _publish_router_contracts() -> list[str]:
    changed: list[str] = []

    video_core_path = "velvet_bot/presentation/telegram/routers/workspace_auf_video.py"
    source = _read(video_core_path)
    source = _append_once(
        source,
        "reference_from_data = _reference_from_data",
        '''# Public cross-module contracts. Domain/state decisions remain in this router
# until the #458 extraction is complete.
reference_from_data = _reference_from_data
truncate_text = _truncate
budget_block_reason = _budget_block_reason
edit_or_answer = _edit_or_answer''',
    )
    if _write(video_core_path, source):
        changed.append(video_core_path)

    video_simple_path = (
        "velvet_bot/presentation/telegram/routers/workspace_auf_video_simple.py"
    )
    source = _read(video_simple_path)
    source = _append_once(
        source,
        "def install_settings_text_renderer(renderer)",
        '''MODEL_NAMES = _MODEL_NAMES
MODEL_ALIASES = _MODEL_ALIASES
MODEL_EXPECTED_IDS = _MODEL_EXPECTED_IDS
settings_text = _settings_text
validated_model = _validated_model
validated_wan_mode = _validated_wan_mode
validated_resolution = _validated_resolution
validated_duration = _validated_duration
validated_audio = _validated_audio
build_request = _build_request
wan_mode_name = _wan_mode_name


def install_settings_text_renderer(renderer) -> None:
    """Install the user-facing settings renderer through an explicit hook."""

    global _settings_text, settings_text
    _settings_text = renderer
    settings_text = renderer''',
    )
    if _write(video_simple_path, source):
        changed.append(video_simple_path)

    wallet_path = "velvet_bot/presentation/telegram/routers/workspace_auf_wallet.py"
    source = _read(wallet_path)
    source = _append_once(
        source,
        "def install_wallet_keyboard_builder(builder)",
        '''wallet_keyboard = _wallet_keyboard


def install_wallet_keyboard_builder(builder) -> None:
    """Install a wallet keyboard decorator through an explicit public hook."""

    global _wallet_keyboard, wallet_keyboard
    _wallet_keyboard = builder
    wallet_keyboard = builder''',
    )
    if _write(wallet_path, source):
        changed.append(wallet_path)

    controller_path = "velvet_bot/presentation/telegram/workspace_home_controller.py"
    source = _read(controller_path)
    source = _append_once(
        source,
        "def install_scoped_auf_handlers(",
        '''require_auf_callback = _require_auf_callback


def install_scoped_auf_handlers(
    *,
    action_handler=None,
    video_handler=None,
) -> None:
    """Install scoped Auf handlers without foreign module attribute mutation."""

    global handle_scoped_auf_action, handle_scoped_auf_video_action
    if action_handler is not None:
        handle_scoped_auf_action = action_handler
    if video_handler is not None:
        handle_scoped_auf_video_action = video_handler''',
    )
    if _write(controller_path, source):
        changed.append(controller_path)
    return changed


def _migrate_auf_portal() -> list[str]:
    path_value = "velvet_bot/app/auf_user_portal_install.py"
    source = _read(path_value)
    source = _add_import(
        source,
        "from velvet_bot.application.media_tasks import task_payload_mapping\n"
        "from velvet_bot.application.workspace_tasks import list_owned_workspace_tasks\n"
        "from velvet_bot.domains.media_generation.model_catalog import (\n"
        "    MODEL_DISPLAY_NAMES,\n"
        "    media_model_display_name,\n"
        ")\n"
        "from velvet_bot.presentation.telegram.state_compatibility import state_value\n",
    )
    source = _replace_regex(
        source,
        r"_MODEL_NAMES = \{.*?\n\}\n_TASK_STATUS",
        "MODEL_NAMES = MODEL_DISPLAY_NAMES\n_TASK_STATUS",
        required=False,
        flags=re.DOTALL,
    )
    source = source.replace("_TASK_PAGE_SIZE", "TASK_PAGE_SIZE")
    source = source.replace("_MODEL_NAMES", "MODEL_NAMES")
    source = _replace_regex(
        source,
        r"\ndef _mapping\(value: object\) -> dict\[str, object\]:.*?\n\n\ndef _state_value\(data: Mapping\[str, object\], key: str\) -> object:.*?\n\n",
        "\n",
        required=False,
        flags=re.DOTALL,
    )
    source = source.replace("_mapping(", "task_payload_mapping(")
    source = source.replace("_state_value(", "state_value(")
    source = _replace_regex(
        source,
        r"async def _load_user_tasks\(.*?\n\n\ndef _task_line",
        '''async def load_user_tasks(
    database,
    *,
    workspace_id: int,
    actor_user_id: int,
    offset: int,
):
    return await list_owned_workspace_tasks(
        database,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        offset=offset,
        page_size=TASK_PAGE_SIZE,
    )


def format_user_task_line''',
        required=False,
        flags=re.DOTALL,
    )
    source = source.replace("def _task_line(", "def format_user_task_line(")
    source = source.replace("_task_line(", "format_user_task_line(")
    source = source.replace(
        "model = MODEL_NAMES.get(model_alias, model_alias or \"Генерация\")",
        "model = media_model_display_name(model_alias)",
    )
    source = source.replace(
        "def _task_list_keyboard(", "def build_user_task_list_keyboard("
    )
    source = source.replace("_task_list_keyboard(", "build_user_task_list_keyboard(")
    source = source.replace("def _render_user_tasks(", "def render_user_tasks(")
    source = source.replace("_render_user_tasks(", "render_user_tasks(")

    replacements = {
        "video_core._reference_from_data": "video_core.reference_from_data",
        "video_router._validated_model": "video_router.validated_model",
        "video_router._validated_wan_mode": "video_router.validated_wan_mode",
        "video_router._validated_resolution": "video_router.validated_resolution",
        "video_router._validated_duration": "video_router.validated_duration",
        "video_router._validated_audio": "video_router.validated_audio",
        "video_router._build_request": "video_router.build_request",
        "video_router._MODEL_NAMES": "video_router.MODEL_NAMES",
        "video_router._MODEL_ALIASES": "video_router.MODEL_ALIASES",
        "video_router._MODEL_EXPECTED_IDS": "video_router.MODEL_EXPECTED_IDS",
        "video_router._wan_mode_name": "video_router.wan_mode_name",
        "video_core._truncate": "video_core.truncate_text",
        "video_core._edit_or_answer": "video_core.edit_or_answer",
        "video_core._budget_block_reason": "video_core.budget_block_reason",
        "controller._require_auf_callback": "controller.require_auf_callback",
        "wallet_router._wallet_keyboard": "wallet_router.wallet_keyboard",
        "video_router._settings_text": "video_router.settings_text",
    }
    for old, new in replacements.items():
        source = source.replace(old, new)

    source = source.replace(
        "    wallet_router._wallet_keyboard = wallet_keyboard_with_tasks\n"
        "    video_router._settings_text = user_settings_text\n"
        "    controller.handle_scoped_auf_action = handle_scoped_auf_user_action\n"
        "    controller.handle_scoped_auf_video_action = handle_scoped_auf_user_video_action\n",
        "    wallet_router.install_wallet_keyboard_builder(wallet_keyboard_with_tasks)\n"
        "    video_router.install_settings_text_renderer(user_settings_text)\n"
        "    controller.install_scoped_auf_handlers(\n"
        "        action_handler=handle_scoped_auf_user_action,\n"
        "        video_handler=handle_scoped_auf_user_video_action,\n"
        "    )\n",
    )
    source = source.replace(
        "def install_auf_user_portal() -> None:\n",
        '''def install_user_tasks_renderer(renderer) -> None:
    """Install a task-list renderer through an explicit public hook."""

    global render_user_tasks
    render_user_tasks = renderer


def install_auf_user_portal() -> None:
''',
        1,
    ) if "def install_user_tasks_renderer(renderer)" not in source else source
    source = _replace_regex(
        source,
        r"__all__ = \(\"install_auf_user_portal\",\)",
        '''__all__ = (
    "MODEL_NAMES",
    "TASK_PAGE_SIZE",
    "build_user_task_list_keyboard",
    "format_user_task_line",
    "install_auf_user_portal",
    "install_user_tasks_renderer",
    "load_user_tasks",
    "render_user_tasks",
)''',
        required=False,
    )
    return [path_value] if _write(path_value, source) else []


def _publish_worker_contracts() -> list[str]:
    changed: list[str] = []
    file_worker_path = "velvet_bot/domains/media_generation/file_delivery_worker.py"
    source = _read(file_worker_path)
    source = _add_import(
        source,
        "from velvet_bot.presentation.telegram.shared.retry import (\n"
        "    TelegramRetryPolicy,\n"
        "    retry_telegram_operation,\n"
        ")\n",
    )
    class_marker = '''class KieGenerationWorker(BaseKieGenerationWorker):
    """Download Kie results, then send Telegram preview and original file."""
'''
    if "def install_delivery_handler(cls, handler)" not in source:
        replacement = class_marker + '''
    @classmethod
    def install_delivery_handler(cls, handler) -> None:
        """Install a delivery implementation through an explicit class hook."""

        cls._deliver_best_effort = handler
'''
        if class_marker not in source:
            raise RuntimeError("file delivery worker class marker is missing")
        source = source.replace(class_marker, replacement, 1)
    source = _replace_regex(
        source,
        r"    async def _send_telegram_with_retry\(.*?\n    async def _download_result",
        '''    async def _send_telegram_with_retry(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[object]],
    ) -> object:
        policy = TelegramRetryPolicy(
            attempts=_RETRY_ATTEMPTS,
            delays=tuple(_retry_delay(attempt) for attempt in range(1, _RETRY_ATTEMPTS)),
        )

        def report_retry(next_attempt: int, error: TelegramAPIError) -> None:
            logger.warning(
                "Telegram Kie delivery retry operation=%s attempt=%s/%s: %s",
                operation_name,
                next_attempt,
                _RETRY_ATTEMPTS,
                error,
            )

        return await retry_telegram_operation(
            operation,
            policy=policy,
            on_retry=report_retry,
        )

    async def _download_result''',
        required=False,
        flags=re.DOTALL,
    )
    source = _append_once(
        source,
        "RESULT_DOWNLOAD_TIMEOUT_SECONDS = _RESULT_DOWNLOAD_TIMEOUT_SECONDS",
        '''DEFAULT_RESULT_USER_AGENT = _DEFAULT_RESULT_USER_AGENT
RESULT_DOWNLOAD_TIMEOUT_SECONDS = _RESULT_DOWNLOAD_TIMEOUT_SECONDS
RESULT_MAX_BYTES = _RESULT_MAX_BYTES
download_result_http = _download_result_http
result_filename = _result_filename''',
    )
    if _write(file_worker_path, source):
        changed.append(file_worker_path)

    worker_path = "velvet_bot/domains/media_generation/worker.py"
    source = _read(worker_path)
    source = _append_once(
        source,
        "ProgressMessage = _ProgressMessage",
        '''ProgressMessage = _ProgressMessage
optional_int = _optional_int''',
    )
    if _write(worker_path, source):
        changed.append(worker_path)

    friendly_path = "velvet_bot/domains/media_generation/friendly_worker.py"
    source = _read(friendly_path)
    source = source.replace(
        "from .file_delivery_worker import _result_filename",
        "from .file_delivery_worker import result_filename",
    )
    source = source.replace(
        "from .worker import _ProgressMessage, _optional_int, render_progress_bar",
        "from .worker import ProgressMessage, optional_int, render_progress_bar",
    )
    source = source.replace("_result_filename(", "result_filename(")
    source = source.replace("_ProgressMessage", "ProgressMessage")
    source = source.replace("_optional_int(", "optional_int(")
    if _write(friendly_path, source):
        changed.append(friendly_path)
    return changed


def _migrate_result_recovery() -> list[str]:
    path_value = "velvet_bot/app/auf_result_delivery_recovery.py"
    source = _read(path_value)
    source = _add_import(
        source,
        "from velvet_bot.application.media_tasks import (\n"
        "    task_payload_mapping,\n"
        "    task_result_urls,\n"
        ")\n"
        "from velvet_bot.application.workspace_tasks import (\n"
        "    get_owned_success_task,\n"
        "    load_task_results,\n"
        ")\n"
        "from velvet_bot.domains.media_generation.model_catalog import (\n"
        "    media_model_display_name,\n"
        ")\n"
        "from velvet_bot.presentation.telegram.shared.retry import (\n"
        "    TelegramRetryPolicy,\n"
        "    retry_telegram_operation,\n"
        ")\n",
    )
    source = source.replace(
        "from velvet_bot.domains.media_generation.file_delivery_worker import (\n"
        "    _DEFAULT_RESULT_USER_AGENT,\n"
        "    _RESULT_DOWNLOAD_TIMEOUT_SECONDS,\n"
        "    _RESULT_MAX_BYTES,\n"
        "    _download_result_http,\n"
        "    _result_filename,\n"
        ")",
        "from velvet_bot.domains.media_generation.file_delivery_worker import (\n"
        "    DEFAULT_RESULT_USER_AGENT,\n"
        "    RESULT_DOWNLOAD_TIMEOUT_SECONDS,\n"
        "    RESULT_MAX_BYTES,\n"
        "    download_result_http,\n"
        "    result_filename,\n"
        ")",
    )
    source = _replace_regex(
        source,
        r"\ndef _mapping\(value: object\) -> dict\[str, object\]:.*?\n\n\ndef _result_urls\(value: object\) -> tuple\[str, \.\.\.\]:.*?\n\n",
        "\n",
        required=False,
        flags=re.DOTALL,
    )
    source = source.replace("_mapping(", "task_payload_mapping(")
    source = source.replace("_result_urls(", "task_result_urls(")
    source = source.replace("_result_filename(", "result_filename(")
    source = source.replace("_download_result_http", "download_result_http")
    source = source.replace(
        "_RESULT_DOWNLOAD_TIMEOUT_SECONDS", "RESULT_DOWNLOAD_TIMEOUT_SECONDS"
    )
    source = source.replace("_RESULT_MAX_BYTES", "RESULT_MAX_BYTES")
    source = source.replace("_DEFAULT_RESULT_USER_AGENT", "DEFAULT_RESULT_USER_AGENT")
    source = _replace_regex(
        source,
        r"async def _send_bot_with_retry\(operation_name: str, operation\):.*?\n\n\nasync def _send_downloaded_result",
        '''async def send_bot_with_retry(operation_name: str, operation):
    policy = TelegramRetryPolicy(
        attempts=_TELEGRAM_RETRY_ATTEMPTS,
        delays=tuple(float(min(8, 2 ** max(0, attempt - 1))) for attempt in range(1, _TELEGRAM_RETRY_ATTEMPTS)),
    )

    def report_retry(next_attempt: int, error: TelegramAPIError) -> None:
        logger.warning(
            "Telegram result redelivery retry operation=%s attempt=%s/%s: %s",
            operation_name,
            next_attempt,
            _TELEGRAM_RETRY_ATTEMPTS,
            error,
        )

    return await retry_telegram_operation(
        operation,
        policy=policy,
        on_retry=report_retry,
    )


async def send_downloaded_result''',
        required=False,
        flags=re.DOTALL,
    )
    renames = {
        "_send_bot_with_retry": "send_bot_with_retry",
        "_send_downloaded_result": "send_downloaded_result",
        "_send_direct_url_fallback": "send_direct_url_fallback",
        "_result_caption": "result_caption",
        "_deliver_record_with_recovery": "deliver_record_with_recovery",
        "_load_owned_success_task": "get_owned_success_task",
        "_redeliver_user_task": "redeliver_user_task",
        "_result_map": "load_task_results",
        "_task_delivery_buttons": "task_delivery_buttons",
        "_render_user_tasks_with_delivery": "render_user_tasks_with_delivery",
        "_delivery_callback": "delivery_callback",
    }
    for old, new in renames.items():
        source = source.replace(old, new)
    source = _replace_regex(
        source,
        r"async def get_owned_success_task\(.*?\n\n\nasync def redeliver_user_task",
        "async def redeliver_user_task",
        required=False,
        flags=re.DOTALL,
    )
    source = _replace_regex(
        source,
        r"async def load_task_results\(database, task_ids: list\[UUID\]\) -> dict\[UUID, object\]:.*?\n\n\ndef task_delivery_buttons",
        "def task_delivery_buttons",
        required=False,
        flags=re.DOTALL,
    )
    source = source.replace("portal._MODEL_NAMES", "portal.MODEL_NAMES")
    source = source.replace("portal._load_user_tasks", "portal.load_user_tasks")
    source = source.replace("portal._TASK_PAGE_SIZE", "portal.TASK_PAGE_SIZE")
    source = source.replace("portal._task_line", "portal.format_user_task_line")
    source = source.replace(
        "portal._task_list_keyboard", "portal.build_user_task_list_keyboard"
    )
    source = source.replace("portal.video_core._edit_or_answer", "portal.video_core.edit_or_answer")
    source = source.replace("controller._require_auf_callback", "controller.require_auf_callback")
    source = source.replace(
        "model = portal.MODEL_NAMES.get(model_alias, model_alias or \"Результат\")",
        "model = media_model_display_name(model_alias, fallback=\"Результат\")",
    )
    source = source.replace(
        "    FriendlyKieGenerationWorker._deliver_best_effort = deliver_record_with_recovery\n"
        "    portal._render_user_tasks = render_user_tasks_with_delivery\n"
        "    controller.handle_scoped_auf_action = handle_scoped_auf_delivery_action\n",
        "    FriendlyKieGenerationWorker.install_delivery_handler(deliver_record_with_recovery)\n"
        "    portal.install_user_tasks_renderer(render_user_tasks_with_delivery)\n"
        "    controller.install_scoped_auf_handlers(\n"
        "        action_handler=handle_scoped_auf_delivery_action\n"
        "    )\n",
    )
    if "def get_redelivery_handler()" not in source:
        source = source.replace(
            "def install_auf_result_delivery_recovery() -> None:\n",
            '''def get_redelivery_handler():
    return redeliver_user_task


def install_redelivery_handler(handler) -> None:
    global redeliver_user_task
    redeliver_user_task = handler


def install_task_delivery_buttons(builder) -> None:
    global task_delivery_buttons
    task_delivery_buttons = builder


def install_auf_result_delivery_recovery() -> None:
''',
            1,
        )
    source = _replace_regex(
        source,
        r"__all__ = \(.*?\)\s*$",
        '''__all__ = (
    "deliver_record_with_recovery",
    "delivery_callback",
    "get_redelivery_handler",
    "install_auf_result_delivery_recovery",
    "install_redelivery_handler",
    "install_task_delivery_buttons",
    "redeliver_user_task",
    "result_caption",
    "task_delivery_buttons",
)''',
        required=False,
        flags=re.DOTALL,
    )
    return [path_value] if _write(path_value, source) else []


def _migrate_active_delivery() -> list[str]:
    path_value = "velvet_bot/app/auf_active_delivery_fix.py"
    source = _read(path_value)
    source = _add_import(
        source,
        "from velvet_bot.application.media_tasks import task_payload_mapping\n"
        "from velvet_bot.domains.media_generation.model_catalog import (\n"
        "    media_model_display_name,\n"
        ")\n",
    )
    source = _replace_regex(
        source,
        r"\ndef _mapping\(value: object\) -> dict\[str, object\]:.*?\n\n",
        "\n",
        required=False,
        flags=re.DOTALL,
    )
    source = source.replace("_mapping(", "task_payload_mapping(")
    source = source.replace("def _provider_task_id(", "def provider_task_id(")
    source = source.replace("_provider_task_id(", "provider_task_id(")
    source = source.replace(
        "def _delivery_buttons_for_all_success(", "def delivery_buttons_for_all_success("
    )
    source = source.replace("recovery._delivery_callback", "recovery.delivery_callback")
    source = source.replace("recovery._load_owned_success_task", "get_owned_success_task")
    source = _add_import(
        source,
        "from velvet_bot.application.workspace_tasks import get_owned_success_task\n",
    )
    source = source.replace("recovery._result_urls", "task_result_urls")
    source = _add_import(
        source,
        "from velvet_bot.application.media_tasks import task_result_urls\n",
    )
    source = source.replace("portal._MODEL_NAMES", "portal.MODEL_NAMES")
    source = source.replace(
        "model = portal.MODEL_NAMES.get(model_alias, model_alias or \"Результат\")",
        "model = media_model_display_name(model_alias, fallback=\"Результат\")",
    )
    source = source.replace(
        "    _ORIGINAL_REDELIVER = recovery._redeliver_user_task\n"
        "    recovery._redeliver_user_task = _redeliver_with_provider_recovery\n"
        "    recovery._task_delivery_buttons = delivery_buttons_for_all_success\n\n"
        "    active_worker = workers.KieGenerationWorker\n"
        "    active_worker._deliver_best_effort = recovery._deliver_record_with_recovery\n",
        "    _ORIGINAL_REDELIVER = recovery.get_redelivery_handler()\n"
        "    recovery.install_redelivery_handler(_redeliver_with_provider_recovery)\n"
        "    recovery.install_task_delivery_buttons(delivery_buttons_for_all_success)\n\n"
        "    active_worker = workers.KieGenerationWorker\n"
        "    active_worker.install_delivery_handler(recovery.deliver_record_with_recovery)\n",
    )
    source = _replace_regex(
        source,
        r"__all__ = \(.*?\)\s*$",
        '''__all__ = (
    "delivery_buttons_for_all_success",
    "install_auf_active_delivery_fix",
    "provider_task_id",
)''',
        required=False,
        flags=re.DOTALL,
    )
    return [path_value] if _write(path_value, source) else []


def _refresh_generated_contracts() -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/inventory_telegram_helpers.py",
            "--write-json",
            "docs/shared_contract_inventory.json",
            "--write-markdown",
            "docs/shared_contract_inventory.md",
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/update_p2_stability_inventory.py",
            "--label",
            "p3-package-shared-contracts",
            "--schema-version",
            "74",
        ],
        cwd=ROOT,
        check=True,
    )
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
    changed: list[str] = []
    changed.extend(_remove_injected_exception_arguments())
    changed.extend(_publish_router_contracts())
    changed.extend(_migrate_auf_portal())
    changed.extend(_publish_worker_contracts())
    changed.extend(_migrate_result_recovery())
    changed.extend(_migrate_active_delivery())
    _refresh_generated_contracts()
    if changed:
        print("Migrated package-wide shared contracts:")
        for path in sorted(set(changed)):
            print(f"- {path}")
    else:
        print("Package-wide shared contract migration is already applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
