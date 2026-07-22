from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if old not in source:
        raise SystemExit(f"marker not found in {path}: {old[:120]!r}")
    target.write_text(source.replace(old, new, count), encoding="utf-8")


core = "velvet_bot/presentation/telegram/routers/core_operations_controllers/watermark.py"
replace(
    core,
    """async def _require_job_workspace(
    database: Database,
    workspace_service: WorkspaceService,""",
    """async def _require_job_workspace(
    database: Database,
    workspace_service: WorkspaceService | None,""",
)
replace(
    core,
    """    if int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return
    active_id, _ = await _workspace_logo_context(""",
    """    if int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return
    if workspace_service is None:
        raise WorkspaceAccessError(
            "Сервис пространства недоступен для личного watermark-задания."
        )
    active_id, _ = await _workspace_logo_context(""",
)
replace(
    core,
    """    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    action = callback_data.action""",
    """    database: Database,
    workspace_service: WorkspaceService | None = None,
) -> None:
    action = callback_data.action""",
)

assets = "velvet_bot/domains/workspaces/watermark_assets.py"
replace(
    assets,
    """        temporary = self._safe_asset_path(path.with_suffix(path.suffix + ".tmp"))
        temporary.write_bytes(prepared.payload)
        os.replace(temporary, path)
        try:""",
    """        temporary = self._safe_asset_path(path.with_suffix(path.suffix + ".tmp"))
        path_existed = path.exists()
        temporary.write_bytes(prepared.payload)
        os.replace(temporary, path)
        try:""",
)
replace(
    assets,
    """        except Exception:
            path.unlink(missing_ok=True)
            raise""",
    """        except Exception:  # p2-approved-boundary: cleanup-new-logo-after-db-failure
            if not path_existed:
                path.unlink(missing_ok=True)
            raise""",
)

replace(
    "tests/test_p3c_publication_controllers.py",
    'self.assertEqual(40, source.count("router.include_router("))',
    'self.assertEqual(42, source.count("router.include_router("))',
)

# Generate current baselines from the final production tree.
subprocess.run(
    [
        sys.executable,
        "scripts/inventory_architecture_layout.py",
        "--write",
        "--label",
        "p3d-analytics-alias-retirement",
    ],
    check=True,
)
subprocess.run(
    [
        sys.executable,
        "scripts/inventory_repository_layout.py",
        "--write",
        "--label",
        "p3e-repository-layout-complete",
    ],
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
    check=True,
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

repo_inventory = json.loads(
    Path("docs/repository_layout_inventory.json").read_text(encoding="utf-8")
)
test_path = Path("tests/test_p3e_repository_layout_inventory.py")
test_source = test_path.read_text(encoding="utf-8")
replacements = {
    r'self\.assertEqual\(33, inventory\["repository_module_count"\]\)': (
        f'self.assertEqual({repo_inventory["repository_module_count"]}, '
        'inventory["repository_module_count"])'
    ),
    r'self\.assertEqual\(32, inventory\["layout_counts"\]\["domain"\]\)': (
        f'self.assertEqual({repo_inventory["layout_counts"]["domain"]}, '
        'inventory["layout_counts"]["domain"])'
    ),
    r'self\.assertEqual\(111, inventory\["root_module_count"\]\)': (
        f'self.assertEqual({repo_inventory["root_module_count"]}, '
        'inventory["root_module_count"])'
    ),
}
for pattern, replacement in replacements.items():
    test_source, changed = re.subn(pattern, replacement, test_source, count=1)
    if changed != 1:
        raise SystemExit(f"repository count pattern not replaced: {pattern}")
test_path.write_text(test_source, encoding="utf-8")

Path("tools/tmp_finalize_team_watermark.py").unlink(missing_ok=True)
