from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_application_installs_canonical_auf_wallet_ui() -> None:
    source = _read("velvet_bot/app/__init__.py")

    assert "install_auf_wallet_ui" in source
    assert "install_meow_wallet_ui" not in source


def test_canonical_wallet_does_not_import_retired_package() -> None:
    paths = (
        "velvet_bot/domains/auf_wallet/__init__.py",
        "velvet_bot/domains/auf_wallet/models.py",
        "velvet_bot/domains/auf_wallet/store.py",
        "velvet_bot/domains/auf_wallet/service.py",
        "velvet_bot/app/auf_wallet_ui_install.py",
        "velvet_bot/presentation/telegram/routers/workspace_auf_wallet.py",
    )

    for path in paths:
        source = _read(path)
        assert "velvet_bot.domains.meow_wallet" not in source, path
        assert "class Meow" not in source, path
        assert "MeowWallet" not in source, path


def test_legacy_wallet_modules_are_only_compatibility_shims() -> None:
    expected = {
        "velvet_bot/domains/meow_wallet/models.py": "AufWallet",
        "velvet_bot/domains/meow_wallet/store.py": "AufWalletRepository",
        "velvet_bot/domains/meow_wallet/service.py": "AufWalletService",
        "velvet_bot/presentation/telegram/routers/workspace_meow_wallet.py": (
            "handle_auf_wallet_action"
        ),
        "velvet_bot/app/meow_wallet_ui_install.py": "install_auf_wallet_ui",
    }

    for path, canonical_name in expected.items():
        source = _read(path)
        assert "Compatibility" in source
        assert canonical_name in source
        assert len(source.splitlines()) <= 45


def test_wallet_ui_has_no_retired_russian_brand() -> None:
    paths = (
        "velvet_bot/presentation/telegram/routers/workspace_auf_wallet.py",
        "velvet_bot/app/auf_wallet_ui_install.py",
        "velvet_bot/domains/auf_wallet/models.py",
        "velvet_bot/domains/auf_wallet/service.py",
        "velvet_bot/domains/auf_wallet/store.py",
        "velvet_bot/presentation/telegram/routers/workspace_meow_root.py",
    )

    for path in paths:
        source = _read(path)
        assert "Мяу" not in source, path
        assert "мяу" not in source, path


def test_dispatcher_exposes_canonical_and_legacy_wallet_di_keys() -> None:
    source = _read("velvet_bot/app/dispatcher.py")

    assert "from velvet_bot.domains.auf_wallet" in source
    assert '"auf_wallet_service": auf_wallet_service' in source
    assert '"meow_wallet_service": auf_wallet_service' in source
