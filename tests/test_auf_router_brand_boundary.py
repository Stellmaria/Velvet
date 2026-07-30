from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "velvet_bot/presentation/telegram/routers"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_canonical_auf_routers_do_not_import_retired_paths() -> None:
    for path in ROUTERS.glob("workspace_auf*.py"):
        if path.name == "workspace_auf_legacy.py":
            continue
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
    legacy = _read(ROUTERS / "workspace_auf_legacy.py")
    controller = _read(
        ROOT / "velvet_bot/presentation/telegram/workspace_home_controller.py"
    )
    assert 'class AufCallback(CallbackData, prefix="auf")' in photo
    assert 'class AufVideoCallback(CallbackData, prefix="aufv")' in video
    assert 'class LegacyMeowCallback(CallbackData, prefix="meow")' in legacy
    assert 'class LegacyMeowVideoCallback(CallbackData, prefix="meowv")' in legacy
    assert 'class MeowForm(StatesGroup)' in legacy
    assert "_auf_callback_filter" in controller
    assert 'F.action.in_({"auf", "meow"})' in controller
    assert "MeowRuntimeForm.waiting_limit" in controller


def test_new_workspace_buttons_use_auf_action() -> None:
    source = _read(ROOT / "velvet_bot/domains/auf_runtime/__init__.py")
    assert 'AUF_WORKSPACE_ACTION = "auf"' in source
    assert 'LEGACY_AUF_WORKSPACE_ACTION = "meow"' in source


def test_photo_flow_writes_auf_state_and_dual_reads_legacy_data() -> None:
    photo = _read(ROUTERS / "workspace_auf_photo.py")
    installer = _read(ROOT / "velvet_bot/app/auf_photo_ui_install.py")
    legacy = _read(ROUTERS / "workspace_auf_legacy.py")
    assert "class AufPhotoForm(StatesGroup)" in photo
    assert "class MeowPhotoForm(StatesGroup)" in legacy
    assert 'key.replace("auf_", "meow_", 1)' in photo
    assert "meow_prompt=" not in photo
    assert "controller._require_meow" not in installer
    assert "controller.handle_scoped_meow_action" not in installer


def test_runtime_keeps_deployed_storage_identifiers() -> None:
    store = _read(ROOT / "velvet_bot/domains/auf_runtime/store.py")
    queue = _read(ROOT / "velvet_bot/domains/auf_runtime/queue.py")
    assert "workspace_meow_settings" in store
    assert "workspace_meow_settings" in queue
    assert "workspace_auf_settings" not in store
    assert "workspace_auf_settings" not in queue


def test_active_routers_write_only_auf_fsm_keys_and_labels() -> None:
    paths = (
        ROUTERS / "workspace_auf.py",
        ROUTERS / "workspace_auf_grs.py",
        ROUTERS / "workspace_auf_balance.py",
        ROUTERS / "workspace_auf_grs_balance.py",
        ROUTERS / "workspace_auf_video.py",
        ROUTERS / "workspace_auf_video_simple.py",
    )
    for path in paths:
        source = _read(path)
        assert "Мяу" not in source, path
        assert "мяу" not in source, path
    core = _read(ROUTERS / "workspace_auf.py")
    for key in (
        "meow_input_mode=",
        "meow_prompt=",
        "meow_references=",
        "meow_model=",
        'data.get("meow_',
    ):
        assert key not in core
    assert 'key.replace("auf_", "meow_", 1)' in core


def test_runtime_branding_monkey_patch_is_not_installed() -> None:
    app = _read(ROOT / "velvet_bot/app/__init__.py")
    assert "install_auf_branding" not in app
