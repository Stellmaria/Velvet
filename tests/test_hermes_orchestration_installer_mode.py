from __future__ import annotations

import stat
from pathlib import Path


def test_canonical_hermes_coder_installer_is_executable() -> None:
    installer = Path("deploy/hermes-coders/install.sh")
    mode = installer.stat().st_mode

    assert mode & stat.S_IXUSR


def test_orchestration_invokes_the_canonical_installer_directly() -> None:
    source = Path("deploy/hermes-orchestration/install.sh").read_text(
        encoding="utf-8"
    )

    assert '"$CODERS_SOURCE/install.sh"' in source
