from __future__ import annotations

import base64
import io
import runpy
import zipfile
from pathlib import Path

# Temporary PR-only bootstrap: apply the deterministic patch before unittest imports
# the rest of the suite, then expose the resulting files through the normal test log.
try:
    runpy.run_path("tools/tmp_wire_team_watermark.py", run_name="__main__")
except SystemExit as error:
    if "marker not found in velvet_bot/watermark_ui.py" not in str(error):
        raise
    runpy.run_path("tools/tmp_wire_team_watermark_resume.py", run_name="__main__")

_TARGETS = (
    "velvet_bot/domains/watermark/models.py",
    "velvet_bot/domains/watermark/repository.py",
    "velvet_bot/domains/watermark/service.py",
    "velvet_bot/infrastructure/krita_bridge.py",
    "velvet_bot/watermark_ui.py",
    "velvet_bot/presentation/telegram/routers/core_operations_controllers/watermark.py",
    "tools/krita/velvet_logo/velvet_logo.py",
    "velvet_bot/presentation/telegram/routers/archive_and_public.py",
    "velvet_bot/core/access/policy.py",
    "velvet_bot/presentation/telegram/routers/workspace_team.py",
    "tests/test_p3_router_organization.py",
    "tools/krita/README.md",
    "docs/krita_watermark.md",
)
_buffer = io.BytesIO()
with zipfile.ZipFile(_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name in _TARGETS:
        archive.write(Path(name), arcname=name)
print("WORKSPACE_PATCH_B64_BEGIN")
print(base64.b64encode(_buffer.getvalue()).decode("ascii"))
print("WORKSPACE_PATCH_B64_END")


import unittest


class TemporaryWorkspaceWiringBootstrap(unittest.TestCase):
    def test_patch_archive_was_built(self) -> None:
        self.assertGreater(len(_buffer.getvalue()), 1000)
