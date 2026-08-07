from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"


def _load_module():
    path = CODERS / "prepare_image_secret_env.py"
    spec = importlib.util.spec_from_file_location("prepare_image_secret_env_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_disabled_fallback_allows_empty_media_secret_file() -> None:
    module = _load_module()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / ".env.hermes"
        target = root / "velvet-media.env"
        source.write_text(
            "CODEX_IMAGE_BYESU_FALLBACK_ENABLED=false\n",
            encoding="utf-8",
        )
        module.write_secret_env(source, target)
        assert target.read_text(encoding="utf-8") == ""
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_enabled_fallback_requires_media_key() -> None:
    module = _load_module()
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / ".env.hermes"
        source.write_text(
            "CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true\n",
            encoding="utf-8",
        )
        try:
            module.render(module.parse_env(source))
        except module.ImageSecretEnvError as error:
            assert "BYESU_MEDIA_GEN_API_KEY" in str(error)
        else:
            raise AssertionError("enabled fallback without media key must fail")


def test_only_media_key_is_written_to_project_secret_file() -> None:
    module = _load_module()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / ".env.hermes"
        target = root / "velvet-media.env"
        media = "m" * 32
        source.write_text(
            "\n".join(
                (
                    "OPENAI_API_KEY=" + "o" * 32,
                    "BYESU_HERMES_CODEX_API_KEY=" + "h" * 32,
                    "BYESU_MEDIA_GEN_API_KEY=" + media,
                    "CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        module.write_secret_env(source, target)
        body = target.read_text(encoding="utf-8")
        assert body == f"BYESU_MEDIA_GEN_API_KEY={media}\n"
        assert "OPENAI_API_KEY" not in body
        assert "BYESU_HERMES_CODEX_API_KEY" not in body
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_target_symlink_is_rejected() -> None:
    module = _load_module()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / ".env.hermes"
        source.write_text(
            "BYESU_MEDIA_GEN_API_KEY=" + "m" * 32 + "\n",
            encoding="utf-8",
        )
        actual = root / "actual.env"
        actual.write_text("", encoding="utf-8")
        target = root / "velvet-media.env"
        target.symlink_to(actual)
        try:
            module.write_secret_env(source, target)
        except module.ImageSecretEnvError:
            pass
        else:
            raise AssertionError("symlinked target must fail closed")


def test_systemd_prepares_secret_before_compose_start_and_reload() -> None:
    unit = (ROOT / "deploy" / "systemd" / "hermes-coders.service").read_text(
        encoding="utf-8"
    )
    prepare = "prepare_image_secret_env.py"
    compose = "compose_image_runtime_env.py /usr/bin/docker compose"
    assert unit.count(prepare) >= 4
    start_prepare = unit.index("ExecStartPre=/usr/bin/python3", unit.index(prepare))
    start_compose = unit.index("ExecStartPre=/usr/bin/python3", start_prepare + 1)
    assert start_prepare < start_compose
    reload_prepare = unit.rindex("ExecReload=/usr/bin/python3", 0, unit.rindex(compose))
    reload_compose = unit.rindex("ExecReload=/usr/bin/python3", 0, unit.rindex(compose) + 1)
    assert reload_prepare <= reload_compose
