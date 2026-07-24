from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one block in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


bundle = Path("velvet_bot/presentation/telegram/routers/archive_and_public.py")
replace_once(
    bundle,
    """from velvet_bot.domains.watermark.workspace_template_runtime import (
    install_workspace_watermark_templates,
)
""",
    "",
)
replace_once(
    bundle,
    """install_workspace_watermark_templates()
apply_workspace_ui_adjustments()
""",
    """apply_workspace_ui_adjustments()
""",
)

reliability = Path("tests/test_workspace_taxonomy_watermark_reliability.py")
replace_once(
    reliability,
    """    def test_watermark_template_is_applied_to_new_workspace_jobs(self) -> None:
        runtime = (
            ROOT
            / "velvet_bot/domains/watermark/workspace_template_runtime.py"
        ).read_text(encoding="utf-8")
        router_bundle = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        self.assertIn("WorkspaceWatermarkTemplateRepository", runtime)
        self.assertIn("settings=settings", runtime)
        self.assertIn("install_workspace_watermark_templates()", router_bundle)
""",
    """    def test_watermark_template_is_applied_without_runtime_service_patch(self) -> None:
        core_watermark = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "watermark.py"
        ).read_text(encoding="utf-8")
        router_bundle = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        runtime = ROOT / "velvet_bot/domains/watermark/workspace_template_runtime.py"

        self.assertIn("WorkspaceWatermarkTemplateRepository(database).get", core_watermark)
        self.assertIn("settings=settings", core_watermark)
        self.assertIn("draft=True", core_watermark)
        self.assertNotIn("install_workspace_watermark_templates", router_bundle)
        self.assertFalse(runtime.exists())
""",
)

boundary_test = Path("tests/test_watermark_draft_persistence_boundary.py")
replace_once(
    boundary_test,
    """        self.assertIn("await service.generate(", source)
        self.assertIn("draft=True", source)

    def test_core_watermark_explicitly_creates_draft_with_workspace_template(self) -> None:
""",
    """        self.assertIn("await service.generate(", source)
        self.assertIn("draft=True", source)
        self.assertFalse(
            (ROOT / "velvet_bot/domains/watermark/workspace_template_runtime.py").exists()
        )

    def test_core_watermark_explicitly_creates_draft_with_workspace_template(self) -> None:
""",
)

runtime = Path("velvet_bot/domains/watermark/workspace_template_runtime.py")
if not runtime.is_file():
    raise RuntimeError("workspace_template_runtime.py is already missing")
runtime.unlink()
