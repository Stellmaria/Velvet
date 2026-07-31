from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_krita_server_image_is_headless_and_non_root() -> None:
    dockerfile = (ROOT / "Dockerfile.krita-server").read_text(encoding="utf-8")

    assert "FROM ubuntu:24.04" in dockerfile
    assert "krita" in dockerfile
    assert "xvfb" in dockerfile
    assert "dbus-x11" in dockerfile
    assert "useradd --create-home --uid 10001 velvet" in dockerfile
    assert "USER velvet" in dockerfile
    assert "enable_velvet_logo=true" in dockerfile


def test_server_compose_isolates_krita_and_shares_only_runtime() -> None:
    compose = (ROOT / "docker-compose.server.yml").read_text(encoding="utf-8")

    assert 'profiles: ["watermark"]' in compose
    assert "dockerfile: Dockerfile.krita-server" in compose
    assert "network_mode: none" in compose
    assert "${VELVET_DATA_DIR:-./server-data}/runtime:/app/runtime" in compose
    assert "KRITA_BRIDGE_DIR: ${KRITA_BRIDGE_DIR:-/app/runtime/krita}" in compose
    assert "cap_drop:" in compose
    assert "no-new-privileges:true" in compose


def test_krita_plugin_prefers_worker_and_server_bridge_environment() -> None:
    plugin = (
        ROOT / "tools/krita/velvet_logo/velvet_logo.py"
    ).read_text(encoding="utf-8")

    worker_env = 'os.getenv("VELVET_KRITA_BRIDGE_DIR", "").strip()'
    server_env = 'os.getenv("KRITA_BRIDGE_DIR", "").strip()'
    fallback = 'str(Path.home() / "VelvetKritaBridge")'
    assert worker_env in plugin
    assert server_env in plugin
    assert fallback in plugin
    assert plugin.index(worker_env) < plugin.index(server_env) < plugin.index(fallback)


def test_krita_entrypoint_uses_virtual_display_without_tcp() -> None:
    entrypoint = (ROOT / "deploy/krita-server/entrypoint.sh").read_text(
        encoding="utf-8"
    )

    assert "dbus-run-session" in entrypoint
    assert "xvfb-run" in entrypoint
    assert "-nolisten tcp" in entrypoint
    assert "/usr/bin/krita --nosplash" in entrypoint


def test_krita_systemd_unit_waits_for_health_and_runs_smoke() -> None:
    unit = (ROOT / "deploy/systemd/velvet-krita.service").read_text(
        encoding="utf-8"
    )

    assert "--profile watermark up -d --build krita" in unit
    assert "wait-compose-health.sh krita" in unit
    assert "krita-smoke.sh .env.server" in unit
    assert "WantedBy=multi-user.target" in unit


def test_server_deploy_reconciles_local_krita_mode() -> None:
    deploy = (ROOT / "deploy/server/deploy.sh").read_text(encoding="utf-8")

    assert 'env.get("KRITA_WATERMARK_ENABLED", "false")' in deploy
    assert 'env.get("KRITA_REMOTE_WORKER_ENABLED", "false")' in deploy
    assert '"${compose[@]}" --profile watermark build --pull krita' in deploy
    assert "wait-compose-health.sh krita" in deploy
    assert "krita-smoke.sh" in deploy


def test_krita_smoke_uses_real_plugin_request_contract() -> None:
    smoke = (ROOT / "deploy/server/krita-smoke.sh").read_text(encoding="utf-8")

    assert '"schema_version": 2' in smoke
    assert '"logo": {"kind": "builtin"' in smoke
    assert '"status") != "ok"' in smoke
    assert 'startswith(b"\\x89PNG\\r\\n\\x1a\\n")' in smoke


def test_installer_enables_local_mode_without_remote_worker() -> None:
    installer = (ROOT / "deploy/server/install-krita-server.sh").read_text(
        encoding="utf-8"
    )

    assert '"KRITA_WATERMARK_ENABLED": "true"' in installer
    assert '"KRITA_REMOTE_WORKER_ENABLED": "false"' in installer
    assert '"KRITA_BRIDGE_DIR": "/app/runtime/krita"' in installer
    assert "systemctl enable --now velvet-krita.service" in installer
