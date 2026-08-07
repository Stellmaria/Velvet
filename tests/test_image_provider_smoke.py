from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"


def _load_module():
    path = CODERS / "image_provider_smoke.py"
    spec = importlib.util.spec_from_file_location("image_provider_smoke_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_disabled_fallback_does_not_require_provider_keys() -> None:
    module = _load_module()
    assert module.validate({"enabled": False}) == "IMAGE_FALLBACK_DISABLED"


def test_enabled_split_key_capabilities_pass() -> None:
    module = _load_module()
    result = module.validate(
        {
            "enabled": True,
            "distinct": True,
            "analysis": {
                "gpt-5.6-sol": True,
                "gpt-5.6-terra": True,
                "gpt-5.6-luna": True,
            },
            "media": {
                "gpt-image-2": True,
                "firefly-gpt-image-2": True,
            },
        }
    )
    assert "SPLIT_KEYS_OK" in result
    assert "MEDIA_MODELS_OK" in result


def test_missing_media_model_fails_closed() -> None:
    module = _load_module()
    try:
        module.validate(
            {
                "enabled": True,
                "distinct": True,
                "analysis": {
                    "gpt-5.6-sol": True,
                    "gpt-5.6-terra": True,
                    "gpt-5.6-luna": True,
                },
                "media": {
                    "gpt-image-2": True,
                    "firefly-gpt-image-2": False,
                },
            }
        )
    except module.ImageProviderSmokeError as error:
        assert "firefly-gpt-image-2" in str(error)
    else:
        raise AssertionError("missing Media Gen capability must fail closed")


def test_systemd_runs_image_provider_smoke_on_start_and_reload() -> None:
    unit = (ROOT / "deploy" / "systemd" / "hermes-coders.service").read_text(
        encoding="utf-8"
    )
    path = "/deploy/hermes-coders/image_provider_smoke.py"
    assert unit.count(path) == 2
    assert "ExecStartPost=/usr/bin/python3" in unit
    assert "ExecReload=/usr/bin/python3" in unit
