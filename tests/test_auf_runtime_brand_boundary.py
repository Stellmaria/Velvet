from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_application_installs_only_canonical_auf_entrypoints() -> None:
    source = _read("velvet_bot/app/__init__.py")

    assert "install_auf_cancel_ui" in source
    assert "install_auf_runtime_dispatcher" in source
    assert "install_auf_workspace_ui" in source
    assert "install_meow_cancel_ui" not in source
    assert "install_meow_runtime_dispatcher" not in source
    assert "install_meow_workspace_ui" not in source


def test_legacy_installers_are_thin_compatibility_shims() -> None:
    expected = {
        "velvet_bot/app/meow_cancel_ui_install.py": "install_auf_cancel_ui",
        "velvet_bot/app/meow_runtime_install.py": "install_auf_runtime_dispatcher",
        "velvet_bot/app/meow_workspace_ui_install.py": "install_auf_workspace_ui",
    }

    for path, canonical_name in expected.items():
        source = _read(path)
        assert "Compatibility shim" in source
        assert canonical_name in source
        assert len(source.splitlines()) <= 12


def test_primary_auf_screens_have_no_retired_russian_brand() -> None:
    paths = (
        "velvet_bot/app/auf_runtime_install.py",
        "velvet_bot/app/auf_workspace_ui_install.py",
        "velvet_bot/presentation/telegram/routers/workspace_meow_root.py",
        "velvet_bot/presentation/telegram/routers/workspace_meow_runtime.py",
        "velvet_bot/presentation/telegram/workspace_home_presentation.py",
        "velvet_bot/domains/meow_runtime/service.py",
    )

    for path in paths:
        source = _read(path)
        assert "Мяу" not in source, path
        assert "мяу" not in source, path


def test_legacy_storage_and_callback_keys_are_centralized() -> None:
    canonical = _read("velvet_bot/domains/auf_runtime/__init__.py")
    home = _read("velvet_bot/presentation/telegram/workspace_home_presentation.py")

    assert 'AUF_MODULE_KEY = "meow"' in canonical
    assert 'AUF_WORKSPACE_ACTION = "meow"' in canonical
    assert 'item.module_key == "meow"' not in home
    assert 'workspace_callback("meow"' not in home


def test_dispatcher_exposes_canonical_and_legacy_di_keys() -> None:
    source = _read("velvet_bot/app/dispatcher.py")

    assert '"auf_runtime_service": auf_runtime_service' in source
    assert '"meow_runtime_service": auf_runtime_service' in source
    assert "from velvet_bot.domains.auf_runtime" in source
