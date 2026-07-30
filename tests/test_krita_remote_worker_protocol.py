from pathlib import Path

import pytest

from tools.krita_worker.worker import WorkerSettings, build_local_request
from velvet_bot.infrastructure.krita_remote_api import KritaRemoteSettings


def test_build_local_request_uses_only_local_bridge_paths(tmp_path: Path) -> None:
    source = tmp_path / "sources" / "job.png"
    output = tmp_path / "outputs" / "job.png"
    response = tmp_path / "responses" / "job.json"
    payload = build_local_request(
        job={
            "job_id": 41,
            "revision": 3,
            "remove_only": False,
            "logo": {"kind": "builtin", "name": "Velvet"},
            "settings": {"position": "bottom_right", "opacity": 70},
        },
        bridge_dir=tmp_path,
        source_path=source,
        output_path=output,
        response_path=response,
        local_logo=None,
    )

    assert payload["request_id"] == "wm-41-r3"
    assert payload["bridge_root"] == str(tmp_path)
    assert payload["source_path"] == str(source)
    assert payload["output_path"] == str(output)
    assert payload["logo"]["kind"] == "builtin"
    assert "lease_token" not in payload


def test_build_local_request_requires_custom_logo_snapshot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="snapshot"):
        build_local_request(
            job={
                "job_id": 5,
                "revision": 1,
                "logo": {"kind": "workspace", "width": 100, "height": 50},
                "settings": {},
            },
            bridge_dir=tmp_path,
            source_path=tmp_path / "source.png",
            output_path=tmp_path / "output.png",
            response_path=tmp_path / "response.json",
            local_logo=None,
        )


def test_remote_server_requires_strong_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRITA_REMOTE_WORKER_ENABLED", "true")
    monkeypatch.setenv("KRITA_REMOTE_WORKER_TOKEN", "short")

    with pytest.raises(RuntimeError, match="не менее 32"):
        KritaRemoteSettings.from_env()


def test_remote_server_defaults_to_separate_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRITA_REMOTE_WORKER_ENABLED", "false")
    monkeypatch.delenv("KRITA_REMOTE_PORT", raising=False)

    settings = KritaRemoteSettings.from_env()

    assert settings.port == 8766
    assert settings.enabled is False


def test_windows_worker_rejects_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VELVET_KRITA_WORKER_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="не менее 32"):
        WorkerSettings.from_env()
