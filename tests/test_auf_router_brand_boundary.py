from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "velvet_bot/presentation/telegram/routers"

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def test_canonical_auf_routers_do_not_import_retired_paths() -> None:
    for path in ROUTERS.glob("workspace_auf*.py"):
        source = _read(path)
        assert "workspace_meow" not in source, path
        assert "class Meow" not in source, path

def test_retired_generation_routers_are_only_compatibility_modules() -> None:
    for path in ROUTERS.glob("workspace_meow*.py"):
        if path.name == "workspace_meow_wallet.py":
            continue
        source = _read(path)
        assert "Compatibility module" in source, path
        assert len(source.splitlines()) <= 24, path

def test_new_callback_protocol_is_auf_and_legacy_is_read_only() -> None:
    photo = _read(ROUTERS / "workspace_auf.py")
    video = _read(ROUTERS / "workspace_auf_video.py")
    controller = _read(
        ROOT / "velvet_bot/presentation/telegram/workspace_home_controller.py"
    )
    assert 'class AufCallback(CallbackData, prefix="auf")' in photo
    assert 'class LegacyMeowCallback(CallbackData, prefix="meow")' in photo
    assert 'class AufVideoCallback(CallbackData, prefix="aufv")' in video
    assert 'class LegacyMeowVideoCallback(CallbackData, prefix="meowv")' in video
    assert "_auf_callback_filter" in controller
    assert 'F.action.in_({"auf", "meow"})' in controller

def test_new_workspace_buttons_use_auf_action() -> None:
    source = _read(ROOT / "velvet_bot/domains/auf_runtime/__init__.py")
    assert 'AUF_WORKSPACE_ACTION = "auf"' in source
    assert 'LEGACY_AUF_WORKSPACE_ACTION = "meow"' in source
