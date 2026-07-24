from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one block in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


core = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/watermark.py"
)
replace_once(
    core,
    "from velvet_bot.domains.watermark.models import WatermarkWorkItem\n",
    "from velvet_bot.domains.watermark.models import WatermarkSettings, WatermarkWorkItem\n",
)
replace_once(
    core,
    "from velvet_bot.domains.workspaces.watermark_assets import WorkspaceWatermarkAssetRepository\n",
    """from velvet_bot.domains.workspaces.watermark_assets import WorkspaceWatermarkAssetRepository
from velvet_bot.domains.workspaces.watermark_templates import (
    WorkspaceWatermarkTemplateRepository,
)
""",
)
replace_once(
    core,
    """    item = await watermark_service.create_job(
        owner_user_id=message.from_user.id,
""",
    """    settings = WatermarkSettings()
    if workspace_id != DEFAULT_WORKSPACE_ID:
        settings = await WorkspaceWatermarkTemplateRepository(database).get(workspace_id)
    item = await watermark_service.create_job(
        owner_user_id=message.from_user.id,
""",
)
replace_once(
    core,
    """        source_file_unique_id=file_unique_id,
        source_path=str(source_path),
        workspace_id=workspace_id,
""",
    """        source_file_unique_id=file_unique_id,
        source_path=str(source_path),
        settings=settings,
        draft=True,
        workspace_id=workspace_id,
""",
)

controller = Path(
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
    "workspace_product_experience.py"
)
text = controller.read_text(encoding="utf-8")
for old, new in (
    ("from dataclasses import replace\n", ""),
    (
        "from velvet_bot.domains.watermark.models import WatermarkSettings, WatermarkWorkItem\n",
        "from velvet_bot.domains.watermark.models import WatermarkWorkItem\n",
    ),
    ("from velvet_bot.domains.watermark.repository import WatermarkRepository\n", ""),
    (
        "from velvet_bot.domains.workspaces.watermark_templates import (\n"
        "    WorkspaceWatermarkTemplateRepository,\n"
        ")\n",
        "",
    ),
):
    if old not in text:
        raise RuntimeError(f"Missing controller import block: {old!r}")
    text = text.replace(old, new, 1)
start = text.index("async def _create_draft_job(")
end = text.index("def _draft_watermark_keyboard(")
text = text[:start] + text[end:]
replacements = (
    (
        """            item = await _service_generate(
                service,
                job_id,
                owner_user_id=owner_user_id,
            )
""",
        """            item = await service.generate(
                job_id,
                owner_user_id=owner_user_id,
            )
""",
    ),
    (
        """                position=callback_data.value,
                enabled=True,
            )
""",
        """                position=callback_data.value,
                enabled=True,
                draft=True,
            )
""",
    ),
    (
        """                color=callback_data.value,
                enabled=True,
            )
""",
        """                color=callback_data.value,
                enabled=True,
                draft=True,
            )
""",
    ),
    (
        """                opacity_delta=int(callback_data.value),
            )
""",
        """                opacity_delta=int(callback_data.value),
                draft=True,
            )
""",
    ),
    (
        """                size_delta=float(callback_data.value),
            )
""",
        """                size_delta=float(callback_data.value),
                draft=True,
            )
""",
    ),
    (
        """                margin_delta=float(callback_data.value),
            )
""",
        """                margin_delta=float(callback_data.value),
                draft=True,
            )
""",
    ),
    (
        """            item = await service.undo(job_id, owner_user_id=owner_user_id)
""",
        """            item = await service.undo(
                job_id,
                owner_user_id=owner_user_id,
                draft=True,
            )
""",
    ),
    (
        """                enabled=False,
            )
""",
        """                enabled=False,
                draft=True,
            )
""",
    ),
    (
        """            color=color,
            enabled=True,
        )
""",
        """            color=color,
            enabled=True,
            draft=True,
        )
""",
    ),
    (
        """    WatermarkService.create_job = _service_create_draft_job  # type: ignore[method-assign]
    WatermarkService.revise = _service_revise_draft  # type: ignore[method-assign]
    WatermarkService.undo = _service_undo_draft  # type: ignore[method-assign]
    setattr(WatermarkService, "generate", _service_generate)

""",
        "",
    ),
)
for old, new in replacements:
    if old not in text:
        raise RuntimeError(f"Missing controller behavior block: {old[:100]!r}")
    text = text.replace(old, new, 1)
controller.write_text(text, encoding="utf-8")
