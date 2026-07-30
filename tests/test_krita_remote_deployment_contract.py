from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_server_compose_exposes_krita_api_only_on_loopback() -> None:
    compose = (ROOT / "docker-compose.krita-remote.yml").read_text(encoding="utf-8")

    assert "127.0.0.1:${KRITA_REMOTE_HOST_PORT:-8766}" in compose
    assert "${KRITA_REMOTE_PORT:-8766}" in compose


def test_remote_worker_migration_has_lease_and_worker_registry() -> None:
    migration = (ROOT / "migrations/z014_krita_remote_workers.sql").read_text(
        encoding="utf-8"
    )

    assert "remote_lease_token_hash" in migration
    assert "remote_lease_expires_at" in migration
    assert "CREATE TABLE IF NOT EXISTS krita_remote_workers" in migration


def test_server_env_keeps_remote_worker_disabled_by_default() -> None:
    env = (ROOT / ".env.krita-remote.example").read_text(encoding="utf-8")

    assert "KRITA_REMOTE_WORKER_ENABLED=false" in env
    assert "KRITA_REMOTE_WORKER_TOKEN=" in env
    assert "KRITA_BRIDGE_DIR=/app/runtime/krita" in env
