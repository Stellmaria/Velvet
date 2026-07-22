from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"marker not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


def replace_between(path: str, start: str, end: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    first = text.index(start)
    last = text.index(end, first)
    target.write_text(text[:first] + new + text[last:], encoding="utf-8")


replace(
    "velvet_bot/domains/watermark/models.py",
    """    created_at: datetime
    updated_at: datetime

    @property
    def archive_media_id""",
    """    created_at: datetime
    updated_at: datetime
    workspace_id: int = 1
    logo_kind: str = "builtin"
    logo_path: str | None = None
    logo_width: float | None = None
    logo_height: float | None = None
    logo_name: str | None = None

    @property
    def archive_media_id""",
)

replace(
    "velvet_bot/domains/watermark/repository.py",
    """        source_path: str,
        settings: WatermarkSettings,
    ) -> WatermarkWorkItem:""",
    """        source_path: str,
        settings: WatermarkSettings,
        workspace_id: int = 1,
        logo_kind: str = "builtin",
        logo_path: str | None = None,
        logo_width: float | None = None,
        logo_height: float | None = None,
        logo_name: str | None = None,
    ) -> WatermarkWorkItem:""",
)
replace(
    "velvet_bot/domains/watermark/repository.py",
    """                    INSERT INTO watermark_jobs (
                        owner_user_id, chat_id, source_message_id,
                        source_file_id, source_file_unique_id, source_path
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)""",
    """                    INSERT INTO watermark_jobs (
                        owner_user_id, chat_id, source_message_id,
                        source_file_id, source_file_unique_id, source_path,
                        workspace_id, logo_kind, logo_path, logo_width,
                        logo_height, logo_name
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6,
                        $7, $8, $9, $10, $11, $12
                    )""",
)
replace(
    "velvet_bot/domains/watermark/repository.py",
    """                    source_file_unique_id,
                    source_path,
                )""",
    """                    source_file_unique_id,
                    source_path,
                    int(workspace_id),
                    logo_kind,
                    logo_path,
                    logo_width,
                    logo_height,
                    logo_name,
                )""",
)
replace(
    "velvet_bot/domains/watermark/repository.py",
    """            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )""",
    """            created_at=row["created_at"],
            updated_at=row["updated_at"],
            workspace_id=(int(row["workspace_id"]) if "workspace_id" in row else 1),
            logo_kind=(str(row["logo_kind"]) if "logo_kind" in row else "builtin"),
            logo_path=(
                str(row["logo_path"])
                if "logo_path" in row and row["logo_path"] is not None
                else None
            ),
            logo_width=(
                float(row["logo_width"])
                if "logo_width" in row and row["logo_width"] is not None
                else None
            ),
            logo_height=(
                float(row["logo_height"])
                if "logo_height" in row and row["logo_height"] is not None
                else None
            ),
            logo_name=(
                str(row["logo_name"])
                if "logo_name" in row and row["logo_name"] is not None
                else None
            ),
        )""",
)

replace(
    "velvet_bot/domains/watermark/service.py",
    """        source_file_unique_id: str | None,
        source_path: str,
    ) -> WatermarkWorkItem:""",
    """        source_file_unique_id: str | None,
        source_path: str,
        workspace_id: int = 1,
        logo_kind: str = "builtin",
        logo_path: str | None = None,
        logo_width: float | None = None,
        logo_height: float | None = None,
        logo_name: str | None = None,
    ) -> WatermarkWorkItem:""",
)
replace(
    "velvet_bot/domains/watermark/service.py",
    """            source_file_unique_id=source_file_unique_id,
            source_path=source_path,
            settings=WatermarkSettings(),
        )""",
    """            source_file_unique_id=source_file_unique_id,
            source_path=source_path,
            settings=WatermarkSettings(),
            workspace_id=workspace_id,
            logo_kind=logo_kind,
            logo_path=logo_path,
            logo_width=logo_width,
            logo_height=logo_height,
            logo_name=logo_name,
        )""",
)

replace(
    "velvet_bot/infrastructure/krita_bridge.py",
    """    sources: Path
    previews: Path""",
    """    sources: Path
    previews: Path
    assets: Path""",
)
replace(
    "velvet_bot/infrastructure/krita_bridge.py",
    """            sources=root_path / "sources",
            previews=root_path / "previews",
        )""",
    """            sources=root_path / "sources",
            previews=root_path / "previews",
            assets=root_path / "assets",
        )""",
)
replace(
    "velvet_bot/infrastructure/krita_bridge.py",
    """        response_path = self.paths.ensure_in(response_path, self.paths.responses)

        payload: dict[str, Any] = {
            "schema_version": 1,""",
    """        response_path = self.paths.ensure_in(response_path, self.paths.responses)

        logo: dict[str, Any] = {
            "kind": item.job.logo_kind,
            "name": item.job.logo_name,
        }
        if item.job.logo_kind != "builtin":
            if not item.job.logo_path or not item.job.logo_width or not item.job.logo_height:
                raise ValueError("Custom watermark job не содержит полного snapshot логотипа.")
            logo_path = self.paths.ensure_in(item.job.logo_path, self.paths.assets)
            if not logo_path.is_file():
                raise ValueError("Файл пользовательского логотипа не найден.")
            logo.update(
                path=str(logo_path),
                width=float(item.job.logo_width),
                height=float(item.job.logo_height),
            )

        payload: dict[str, Any] = {
            "schema_version": 2,""",
)
replace(
    "velvet_bot/infrastructure/krita_bridge.py",
    """            "revision": revision,
            "bridge_root": str(self.paths.root),""",
    """            "revision": revision,
            "workspace_id": item.job.workspace_id,
            "bridge_root": str(self.paths.root),
            "logo": logo,""",
)

replace_between(
    "velvet_bot/watermark_ui.py",
    "def _settings_rows(item: WatermarkWorkItem)",
    "\n\ndef build_archive_watermark_review_keyboard",
    '''def _settings_rows(item: WatermarkWorkItem) -> list[list[InlineKeyboardButton]]:
    job_id = item.job.id
    rows = [
        [
            _button("↖️", "position", job_id, "top_left"),
            _button("↗️", "position", job_id, "top_right"),
            _button("↙️", "position", job_id, "bottom_left"),
            _button("↘️", "position", job_id, "bottom_right"),
        ]
    ]
    if item.job.logo_kind == "builtin":
        rows.append(
            [
                _button("⚪ Белый", "color", job_id, "#ffffff"),
                _button("⚫ Чёрный", "color", job_id, "#000000"),
                _button("◐ Авто", "color", job_id, "auto"),
                _button("🎨 HEX", "custom_color", job_id),
            ]
        )
    rows.extend(
        [
            [_button("Прозр. −", "opacity", job_id, "-10"), _button("Прозр. +", "opacity", job_id, "10")],
            [_button("Размер −", "size", job_id, "-1.5"), _button("Размер +", "size", job_id, "1.5")],
            [_button("Отступ −", "margin", job_id, "-0.5"), _button("Отступ +", "margin", job_id, "0.5")],
            [_button("↩️ Предыдущая версия", "undo", job_id), _button("🚫 Без знака", "remove", job_id)],
        ]
    )
    return rows
''',
)
replace(
    "velvet_bot/watermark_ui.py",
    '''    color = settings.color.upper() if settings.enabled else "без знака"
    status = status_text or item.revision.status''',
    '''    color = settings.color.upper() if settings.enabled else "без знака"
    logo = (
        "стандартный Velvet"
        if item.job.logo_kind == "builtin"
        else f"{item.job.logo_kind.upper()}: {item.job.logo_name or 'workspace logo'}"
    )
    status = status_text or item.revision.status''',
)
replace(
    "velvet_bot/watermark_ui.py",
    '''        f"Версия: <b>{item.revision.revision}</b>\n"
        f"Положение:''',
    '''        f"Версия: <b>{item.revision.revision}</b>\n"
        f"Пространство: <code>{item.job.workspace_id}</code>\n"
        f"Логотип: <b>{escape(logo)}</b>\n"
        f"Положение:''',
)

core = "velvet_bot/presentation/telegram/routers/core_operations_controllers/watermark.py"
replace(
    core,
    """from velvet_bot.database import Database
from velvet_bot.domains.public_archive.watermark_repository import (""",
    """from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_assets import WorkspaceWatermarkAssetRepository
from velvet_bot.domains.public_archive.watermark_repository import (""",
)
replace(
    core,
    """def _build_service(bot: Bot, database: Database) -> WatermarkService:
    return WatermarkService(
        bot=bot,
        repository=WatermarkRepository(database),
        bridge=KritaBridge(default_krita_bridge_dir()),
    )


async def _wake_krita""",
    '''def _build_service(bot: Bot, database: Database) -> WatermarkService:
    return WatermarkService(
        bot=bot,
        repository=WatermarkRepository(database),
        bridge=KritaBridge(default_krita_bridge_dir()),
    )


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _workspace_logo_context(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    user_id: int,
):
    global_owner = _is_global_owner(user_id)
    workspace = await workspace_service.resolve_active_workspace(
        user_id=user_id,
        global_owner=global_owner,
    )
    if workspace.id == DEFAULT_WORKSPACE_ID:
        return DEFAULT_WORKSPACE_ID, None
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="editor",
        global_owner=global_owner,
    )
    async with database.acquire() as connection:
        enabled = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'watermark'
            """,
            workspace.id,
        )
    if not enabled:
        raise WorkspaceAccessError("Модуль watermark выключен или не разрешён Стэл.")
    asset = await WorkspaceWatermarkAssetRepository(database).get(workspace.id)
    return workspace.id, asset


async def _require_job_workspace(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    user_id: int,
    workspace_id: int,
) -> None:
    if int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return
    active_id, _ = await _workspace_logo_context(
        database, workspace_service, user_id=user_id
    )
    if active_id != int(workspace_id):
        raise WorkspaceAccessError(
            "Задание относится не к активному пространству. Откройте его заново."
        )


async def _wake_krita''',
)
replace(
    core,
    """    bot: Bot,
    watermark_service: WatermarkService,
) -> WatermarkWorkItem | None:
    source = _source_file(source_message)""",
    '''    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
    watermark_service: WatermarkService,
) -> WatermarkWorkItem | None:
    try:
        workspace_id, logo_asset = await _workspace_logo_context(
            database,
            workspace_service,
            user_id=int(message.from_user.id),
        )
    except WorkspaceAccessError as error:
        await message.answer(f"❌ {escape(str(error))}")
        return None
    source = _source_file(source_message)''',
)
replace(
    core,
    """        source_file_unique_id=file_unique_id,
        source_path=str(source_path),
    )""",
    '''        source_file_unique_id=file_unique_id,
        source_path=str(source_path),
        workspace_id=workspace_id,
        logo_kind=(logo_asset.asset_kind if logo_asset is not None else "builtin"),
        logo_path=(logo_asset.local_path if logo_asset is not None else None),
        logo_width=(logo_asset.width if logo_asset is not None else None),
        logo_height=(logo_asset.height if logo_asset is not None else None),
        logo_name=(logo_asset.file_name if logo_asset is not None else None),
    )''',
)

# Add WorkspaceService to the three message/callback handlers that need it.
replace(
    core,
    """    bot: Bot,
    database: Database,
) -> None:
    if not _watermark_enabled():""",
    """    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not _watermark_enabled():""",
    1,
)
replace(
    core,
    """        bot=bot,
        watermark_service=_build_service(bot, database),
    )""",
    """        bot=bot,
        database=database,
        workspace_service=workspace_service,
        watermark_service=_build_service(bot, database),
    )""",
    1,
)
replace(
    core,
    """    bot: Bot,
    database: Database,
) -> None:
    if not _watermark_enabled():""",
    """    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not _watermark_enabled():""",
    1,
)
replace(
    core,
    """        bot=bot,
        watermark_service=_build_service(bot, database),
    )""",
    """        bot=bot,
        database=database,
        workspace_service=workspace_service,
        watermark_service=_build_service(bot, database),
    )""",
    1,
)
replace(
    core,
    """    bot: Bot,
    database: Database,
) -> None:
    if not _watermark_enabled():
        await message.answer("Krita bridge выключен.")""",
    """    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if not _watermark_enabled():
        await message.answer("Krita bridge выключен.")""",
    1,
)
replace(
    core,
    '''    service = _build_service(bot, database)
    color = (message.text or "").strip()
    try:
        item = await service.revise(''',
    '''    service = _build_service(bot, database)
    color = (message.text or "").strip()
    try:
        current = await service.get_current(
            watermark_job_id, owner_user_id=message.from_user.id
        )
        await _require_job_workspace(
            database,
            workspace_service,
            user_id=message.from_user.id,
            workspace_id=current.job.workspace_id,
        )
        item = await service.revise(''',
)
replace(
    core,
    """    bot: Bot,
    database: Database,
) -> None:
    action = callback_data.action""",
    """    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    action = callback_data.action""",
)
replace(
    core,
    """    owner_user_id = callback.from_user.id
    job_id = callback_data.job_id

    if action == "archive_edit":""",
    '''    owner_user_id = callback.from_user.id
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

    if action == "archive_edit":''',
)

plugin = "tools/krita/velvet_logo/velvet_logo.py"
replace(plugin, "import json\nimport os\nimport re", "import base64\nimport json\nimport os\nimport re\nimport xml.etree.ElementTree as ET")
replace(
    plugin,
    '        for name in ("requests", "responses", "outputs", "sources", "previews"):',
    '        for name in ("requests", "responses", "outputs", "sources", "previews", "assets"):')
replace(
    plugin,
    '''                settings = self._normalize(request.get("settings") or {})
                self._apply(document, settings)''',
    '''                settings = self._normalize(request.get("settings") or {})
                self._apply(document, settings, request.get("logo") or {})''',
)
replace_between(
    plugin,
    "    def _apply(self, document, raw_settings: dict[str, Any]) -> None:",
    "\n    def _auto_color",
    '''    def _apply(
        self,
        document,
        raw_settings: dict[str, Any],
        logo: dict[str, Any] | None = None,
    ) -> None:
        settings = self._normalize(raw_settings)
        logo = logo or {"kind": "builtin"}
        color = settings["color"]
        if logo.get("kind", "builtin") == "builtin" and color == "auto":
            color = self._auto_color(document, settings)
        settings = dict(settings, color=color)
        self._remove_layers(document)
        root = document.rootNode()
        logo_name = str(logo.get("name") or logo.get("kind") or "builtin")
        layer = document.createVectorLayer(f"{self.LAYER_PREFIX} ({logo_name})")
        root.addChildNode(layer, None)
        shapes = layer.addShapesFromSvg(self._build_svg(document, settings, logo))
        if not shapes:
            root.removeChildNode(layer)
            raise RuntimeError("Krita не смогла импортировать SVG логотипа.")
        layer.setOpacity(round(255 * settings["opacity"] / 100.0))
        layer.setLocked(settings["lock"])
        document.setActiveNode(layer)
        document.setModified(True)
        document.refreshProjection()

    def _build_svg(
        self,
        document,
        settings: dict[str, Any],
        logo: dict[str, Any] | None = None,
    ) -> str:
        logo = logo or {"kind": "builtin"}
        width = float(document.width())
        height = float(document.height())
        points = 72.0 / float(document.resolution() or 72.0)
        canvas_width, canvas_height = width * points, height * points
        kind = str(logo.get("kind") or "builtin").casefold()
        logo_width = width * settings["size"] / 100.0 * points
        margin = width * settings["margin"] / 100.0 * points
        vertical, horizontal = self._parts(settings["position"])
        if kind == "builtin":
            logo_height = logo_width * self.LOGO_ASPECT
            x = self._axis(horizontal, canvas_width, logo_width, margin)
            y = self._axis(vertical, canvas_height, logo_height, margin)
            scale = logo_width / 1055.0
            start = LOGO_SVG.index("<path")
            path = LOGO_SVG[start:LOGO_SVG.index("/>", start) + 2].replace(
                "#000000", settings["color"]
            )
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width}pt" '
                f'height="{canvas_height}pt" viewBox="0 0 {canvas_width} {canvas_height}">'
                f'<g transform="translate({x} {y}) scale({scale}) translate(-99 -250)">'
                f"{path}</g></svg>"
            )

        source = self._safe_path(logo.get("path"), required=True)
        assert source is not None
        assets_root = (self._bridge_root / "assets").resolve()
        try:
            source.relative_to(assets_root)
        except ValueError as error:
            raise ValueError("Пользовательский логотип находится вне assets.") from error
        source_width = float(logo.get("width") or 0)
        source_height = float(logo.get("height") or 0)
        if source_width <= 0 or source_height <= 0:
            raise ValueError("Некорректные размеры пользовательского логотипа.")
        logo_height = logo_width * source_height / source_width
        x = self._axis(horizontal, canvas_width, logo_width, margin)
        y = self._axis(vertical, canvas_height, logo_height, margin)
        if kind == "png":
            encoded = base64.b64encode(source.read_bytes()).decode("ascii")
            body = (
                f'<image x="{x}" y="{y}" width="{logo_width}" height="{logo_height}" '
                f'preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{encoded}" />'
            )
        elif kind == "svg":
            root = ET.fromstring(source.read_bytes())
            inner = "".join(ET.tostring(child, encoding="unicode") for child in list(root))
            view_box = root.attrib.get("viewBox") or f"0 0 {source_width} {source_height}"
            body = (
                f'<svg x="{x}" y="{y}" width="{logo_width}" height="{logo_height}" '
                f'viewBox="{view_box}" preserveAspectRatio="xMidYMid meet">{inner}</svg>'
            )
        else:
            raise ValueError("Неизвестный тип пользовательского логотипа.")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{canvas_width}pt" '
            f'height="{canvas_height}pt" viewBox="0 0 {canvas_width} {canvas_height}">'
            f"{body}</svg>"
        )
''',
)

replace(
    "velvet_bot/presentation/telegram/routers/archive_and_public.py",
    '''from velvet_bot.presentation.telegram.routers.workspace_admin import (
    router as workspace_admin_router,
)''',
    '''from velvet_bot.presentation.telegram.routers.workspace_admin import (
    router as workspace_admin_router,
)
from velvet_bot.presentation.telegram.routers.workspace_team import (
    router as workspace_team_router,
)
from velvet_bot.presentation.telegram.routers.workspace_watermark import (
    router as workspace_watermark_router,
)''',
)
replace(
    "velvet_bot/presentation/telegram/routers/archive_and_public.py",
    '''router.include_router(workspace_admin_router)
router.include_router(workspaces_router)''',
    '''router.include_router(workspace_admin_router)
router.include_router(workspace_team_router)
router.include_router(workspace_watermark_router)
router.include_router(workspaces_router)''',
)

replace(
    "velvet_bot/core/access/policy.py",
    '''        "discussionstats",
        "prompt",''',
    '''        "discussionstats",
        "watermark",
        "prompt",''',
)
replace(
    "velvet_bot/core/access/policy.py",
    'WORKSPACE_MEMBER_CALLBACK_PREFIXES = ("wsp:", "wch:", "ref:", "pubq:", "dash:")',
    '''WORKSPACE_MEMBER_CALLBACK_PREFIXES = (
    "wsp:", "wch:", "ref:", "pubq:", "dash:", "wteam:", "wlogo:", "wm:"
)''',
)

replace(
    "velvet_bot/presentation/telegram/routers/workspace_team.py",
    '''        await callback.answer()
        return

    target = await repository.get_member(''',
    '''        await callback.answer()
        return
    if action == "addrole":
        try:
            role = cast(WorkspaceRole, callback_data.role)
            if role not in ROLE_LABELS:
                raise ValueError("Неизвестная роль команды.")
            await service.add_member(
                workspace_id=workspace.id,
                actor_user_id=actor_id,
                user_id=callback_data.user_id,
                role=role,
                global_owner=_is_global_owner(actor_id),
            )
        except (WorkspaceAccessError, ValueError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer(f"Участник добавлен: {ROLE_LABELS[role]}.")
        members = await service.list_members(
            workspace_id=workspace.id,
            actor_user_id=actor_id,
            global_owner=_is_global_owner(actor_id),
        )
        await _edit(
            callback,
            text=format_team(workspace_name=workspace.name, members=members),
            reply_markup=build_team_keyboard(workspace_id=workspace.id, members=members),
        )
        return

    target = await repository.get_member(''',
)
replace_between(
    "velvet_bot/presentation/telegram/routers/workspace_team.py",
    '\n\n@router.callback_query(WorkspaceTeamCallback.filter(F.action == "addrole"))',
    '\n\n__all__ = ("router",)',
    "",
)

replace(
    "tests/test_p3_router_organization.py",
    '''    "velvet_bot.presentation.telegram.routers.workspace_reference_library",
    "velvet_bot.presentation.telegram.routers.workspaces",''',
    '''    "velvet_bot.presentation.telegram.routers.workspace_reference_library",
    "velvet_bot.presentation.telegram.routers.workspace_team",
    "velvet_bot.presentation.telegram.routers.workspace_watermark",
    "velvet_bot.presentation.telegram.routers.workspaces",''',
)

readme = Path("tools/krita/README.md")
readme.write_text(
    readme.read_text(encoding="utf-8")
    + """

## Пользовательские логотипы workspace

Bridge schema v2 принимает snapshot логотипа из `assets/`. Поддерживаются очищенный SVG и прозрачный PNG. Файл обязан находиться внутри bridge-каталога; плагин не читает внешние URL и не меняет исходник. Цветовые настройки применяются только к встроенному логотипу Velvet, пользовательский asset сохраняет собственные цвета.
""",
    encoding="utf-8",
)
docs = Path("docs/krita_watermark.md")
docs.write_text(
    docs.read_text(encoding="utf-8")
    + """

## Логотип пространства

Владелец или администратор личного workspace может загрузить SVG либо PNG/WebP с прозрачным фоном через модуль `💧 Watermark`. SVG очищается от scripts, event handlers, `DOCTYPE`, entities и внешних ресурсов. Raster нормализуется в RGBA PNG и обязан содержать реальные прозрачные пиксели. Каждый watermark job сохраняет snapshot выбранного файла, поэтому последующая замена логотипа не изменяет уже созданные задания.
""",
    encoding="utf-8",
)

Path(".github/workflows/tmp-wire-team-watermark.yml").unlink(missing_ok=True)
Path("tools/tmp_wire_team_watermark.py").unlink(missing_ok=True)
