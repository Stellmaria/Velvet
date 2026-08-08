from __future__ import annotations

import logging
import os
from typing import Any

from velvet_bot.supervisor_client import (
    SupervisorClient,
    SupervisorClientError,
    build_supervisor_client,
)

logger = logging.getLogger(__name__)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "да"})


def _uses_local_server_worker() -> bool:
    watermark_enabled = (
        os.getenv("KRITA_WATERMARK_ENABLED", "false").strip().casefold()
        in _TRUE_VALUES
    )
    remote_enabled = (
        os.getenv("KRITA_REMOTE_WORKER_ENABLED", "false").strip().casefold()
        in _TRUE_VALUES
    )
    bridge_dir = os.getenv("KRITA_BRIDGE_DIR", "").strip().rstrip("/")
    local_bridge = (
        bridge_dir == "/app/runtime/krita"
        or bridge_dir.startswith("/app/runtime/krita/")
    )
    return watermark_enabled and not remote_enabled and local_bridge


class KritaSupervisorClient(SupervisorClient):
    async def ensure_krita(self) -> dict[str, Any]:
        return await self._request("POST", "/v1/krita/ensure", {})

    async def touch_krita(self) -> dict[str, Any]:
        return await self._request("POST", "/v1/krita/touch", {})

    async def stop_krita(self, *, force: bool = False) -> dict[str, Any]:
        return await self._request("POST", "/v1/krita/stop", {"force": force})

    async def krita_status(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/krita/status")


def build_krita_supervisor_client() -> KritaSupervisorClient | None:
    base = build_supervisor_client()
    if base is None:
        return None
    return KritaSupervisorClient(
        base_url=base.base_url,
        token=base.token,
        timeout_seconds=base.timeout_seconds,
    )


async def wake_krita(*, context: str = "watermark") -> str | None:
    if _uses_local_server_worker():
        logger.debug(
            "Krita wake skipped for local server worker context=%s",
            context,
        )
        return None
    client = build_krita_supervisor_client()
    if client is None:
        return None
    try:
        await client.ensure_krita()
    except SupervisorClientError as error:
        logger.warning("Could not wake Krita for %s: %s", context, error)
        return str(error)
    return None


__all__ = (
    "KritaSupervisorClient",
    "build_krita_supervisor_client",
    "wake_krita",
)
