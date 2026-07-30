from __future__ import annotations

from html import escape

from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.presentation.telegram.routers import workspace_auf_photo as photo_router

_INSTALLED = False
_ORIGINAL_INPUT_TEXT = photo_router._input_text


async def _load_private_sources(
    database,
    *,
    user_id: int,
    active_workspace_id: int,
):
    include_system = int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID
    async with database.acquire() as connection:
        return await connection.fetch(
            """
            SELECT DISTINCT workspace.id, workspace.name, workspace.is_system
            FROM workspaces AS workspace
            LEFT JOIN workspace_members AS membership
              ON membership.workspace_id = workspace.id
             AND membership.user_id = $1::BIGINT
            WHERE (
                    membership.user_id IS NOT NULL
                 OR workspace.id = $2::BIGINT
                 OR ($3::BOOLEAN AND workspace.is_system = TRUE)
            )
              AND (workspace.is_system = FALSE OR $3::BOOLEAN)
            ORDER BY workspace.is_system DESC, workspace.name, workspace.id
            LIMIT 30
            """,
            int(user_id),
            int(active_workspace_id),
            include_system,
        )


async def _can_access_private_source(
    database,
    *,
    user_id: int,
    active_workspace_id: int,
    source_workspace_id: int,
) -> bool:
    include_system = int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID
    async with database.acquire() as connection:
        return bool(
            await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM workspaces AS workspace
                    LEFT JOIN workspace_members AS membership
                      ON membership.workspace_id = workspace.id
                     AND membership.user_id = $1::BIGINT
                    WHERE workspace.id = $3::BIGINT
                      AND (
                            membership.user_id IS NOT NULL
                         OR workspace.id = $2::BIGINT
                         OR ($4::BOOLEAN AND workspace.is_system = TRUE)
                      )
                      AND (workspace.is_system = FALSE OR $4::BOOLEAN)
                )
                """,
                int(user_id),
                int(active_workspace_id),
                int(source_workspace_id),
                include_system,
            )
        )


def _private_source_keyboard(workspace_id: int, sources):
    rows = [
        [
            photo_router._button(
                (
                    f"Служебная база · {row['name']}"
                    if bool(row["is_system"])
                    else str(row["name"])
                )[:64],
                "photo_ref_workspace",
                workspace_id=workspace_id,
                item_id=int(row["id"]),
            )
        ]
        for row in sources
    ]
    rows.extend(
        [
            [photo_router._button("К вводу", "photo_input_back", workspace_id=workspace_id)],
            [photo_router._button("Отмена", "cancel", workspace_id=workspace_id)],
        ]
    )
    return photo_router.InlineKeyboardMarkup(inline_keyboard=rows)


def _private_input_text(prompt, references) -> str:
    text = _ORIGINAL_INPUT_TEXT(prompt, references)
    return text.replace("из архива", "из личной базы").replace(
        "референсы персонажа из архива",
        "референсы персонажа из личной базы",
    )


def _private_review_text(prompt, references) -> str:
    uploaded = sum(reference.source == "upload" for reference in references)
    stored = len(references) - uploaded
    return (
        "<b>Проверьте фото и текст</b>\n\n"
        f"Фото: <b>{len(references)}</b>\n"
        f"Отправлено: <b>{uploaded}</b> · из базы: <b>{stored}</b>\n\n"
        f"<b>Текст</b>\n{escape(photo_router._truncate(prompt, 3000))}\n\n"
        "После подтверждения выбираются модель, качество и соотношение сторон."
    )


def install_auf_reference_privacy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    photo_router._load_sources = _load_private_sources
    photo_router._can_access_source = _can_access_private_source
    photo_router._source_keyboard = _private_source_keyboard
    photo_router._input_text = _private_input_text
    photo_router._review_text = _private_review_text
    _INSTALLED = True


__all__ = ("install_auf_reference_privacy",)
