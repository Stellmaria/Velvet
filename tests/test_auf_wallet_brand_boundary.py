from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

def test_canonical_wallet_never_imports_retired_package() -> None:
    for path in (
        "velvet_bot/domains/auf_wallet/__init__.py",
        "velvet_bot/domains/auf_wallet/models.py",
        "velvet_bot/domains/auf_wallet/store.py",
        "velvet_bot/domains/auf_wallet/service.py",
        "velvet_bot/domains/auf_wallet/pricing.py",
        "velvet_bot/domains/auf_wallet/purchase.py",
        "velvet_bot/domains/auf_wallet/charged_queue.py",
        "velvet_bot/presentation/telegram/routers/workspace_auf_wallet.py",
        "velvet_bot/app/auf_wallet_ui_install.py",
    ):
        source = _read(path)
        assert "velvet_bot.domains.meow_wallet" not in source, path
        assert "class Meow" not in source, path

def test_retired_wallet_files_are_only_compatibility_shims() -> None:
    limits = {
        "velvet_bot/domains/meow_wallet/models.py": 40,
        "velvet_bot/domains/meow_wallet/store.py": 12,
        "velvet_bot/domains/meow_wallet/service.py": 20,
        "velvet_bot/domains/meow_wallet/pricing.py": 20,
        "velvet_bot/domains/meow_wallet/purchase.py": 25,
        "velvet_bot/domains/meow_wallet/charged_queue.py": 16,
        "velvet_bot/presentation/telegram/routers/workspace_meow_wallet.py": 10,
        "velvet_bot/app/meow_wallet_ui_install.py": 8,
    }
    for path, maximum in limits.items():
        source = _read(path)
        assert "Compatibility" in source, path
        assert len(source.splitlines()) <= maximum, path

def test_production_uses_canonical_wallet_imports() -> None:
    dispatcher = _read("velvet_bot/app/dispatcher.py")
    installer = _read("velvet_bot/app/auf_wallet_ui_install.py")
    assert "from velvet_bot.domains.auf_wallet" in dispatcher
    assert "workspace_auf_wallet" in installer
    assert "meow_wallet_service" not in installer
    assert "meow_purchase_service" not in installer
