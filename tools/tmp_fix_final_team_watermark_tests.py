from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if old not in source:
        raise SystemExit(f"marker not found in {path}: {old[:140]!r}")
    target.write_text(source.replace(old, new, count), encoding="utf-8")


replace(
    "tests/test_workspace_archive_isolation.py",
    '''            await connection.execute(
                "DELETE FROM workspace_members WHERE workspace_id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                "DELETE FROM workspace_channels WHERE workspace_id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )
            await connection.execute(
                "DELETE FROM workspaces WHERE id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )''',
    '''            # Deleting the workspace is the product operation. Memberships,
            # channels and the rest of the tenant graph are removed by FK cascades.
            # Direct owner deletion is intentionally blocked by migration 909.
            await connection.execute(
                "DELETE FROM workspaces WHERE id <> $1::BIGINT",
                DEFAULT_WORKSPACE_ID,
            )''',
)

replace(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/watermark.py",
    '''    service = _build_service(bot, database)
    owner_user_id = callback.from_user.id
    job_id = callback_data.job_id
    try:
        current = await service.get_current(job_id, owner_user_id=owner_user_id)
        await _require_job_workspace(
            database,
            workspace_service,
            user_id=owner_user_id,
            workspace_id=current.job.workspace_id,
        )
    except (WorkspaceAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    if action == "archive_edit":
        try:
            item = await service.get_current(
                job_id,
                owner_user_id=owner_user_id,
            )
        except ValueError:
            await callback.answer("Архивное задание не найдено.", show_alert=True)
            return
        if item.job.archive_media_id is None:
            await callback.answer("Архивное задание не найдено.", show_alert=True)
            return
        await callback.answer("Настройки открыты.")
        await _safe_edit(
            callback,
            format_watermark_caption(item, status_text="измените шаблон"),
            item,
            keyboard=build_archive_watermark_edit_keyboard(item),
        )
        return
''',
    '''    service = _build_service(bot, database)
    owner_user_id = callback.from_user.id
    job_id = callback_data.job_id

    if action == "archive_edit":
        try:
            item = await service.get_current(
                job_id,
                owner_user_id=owner_user_id,
            )
            await _require_job_workspace(
                database,
                workspace_service,
                user_id=owner_user_id,
                workspace_id=getattr(
                    item.job,
                    "workspace_id",
                    DEFAULT_WORKSPACE_ID,
                ),
            )
        except (WorkspaceAccessError, ValueError):
            # Do not reveal whether an archive job exists for another owner/workspace.
            await callback.answer("Архивное задание не найдено.", show_alert=True)
            return
        if item.job.archive_media_id is None:
            await callback.answer("Архивное задание не найдено.", show_alert=True)
            return
        await callback.answer("Настройки открыты.")
        await _safe_edit(
            callback,
            format_watermark_caption(item, status_text="измените шаблон"),
            item,
            keyboard=build_archive_watermark_edit_keyboard(item),
        )
        return

    try:
        current = await service.get_current(job_id, owner_user_id=owner_user_id)
        await _require_job_workspace(
            database,
            workspace_service,
            user_id=owner_user_id,
            workspace_id=getattr(
                current.job,
                "workspace_id",
                DEFAULT_WORKSPACE_ID,
            ),
        )
    except (WorkspaceAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return
''',
)

subprocess.run(
    [
        sys.executable,
        "scripts/update_p2_stability_inventory.py",
        "--label",
        "workspace-team-watermark",
        "--schema-version",
        "52",
    ],
    check=True,
)

Path("tools/tmp_fix_final_team_watermark_tests.py").unlink(missing_ok=True)
