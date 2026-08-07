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


def test_orchestration_reuses_canonical_launcher_env_for_coder_compose() -> None:
    source = Path("deploy/hermes-orchestration/install.sh").read_text(
        encoding="utf-8"
    )

    assert 'CODERS_LAUNCHER_ENV="$CODERS_ROOT/launcher.env"' in source
    assert 'Canonical coder launcher env отсутствует или небезопасен' in source
    assert source.count('docker compose --env-file "$CODERS_LAUNCHER_ENV"') == 2
    assert 'HERMES_SANDBOX_GID=' not in source
