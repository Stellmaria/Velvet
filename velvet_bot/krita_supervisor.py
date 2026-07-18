from __future__ import annotations

from typing import Any

from velvet_bot.supervisor_client import SupervisorClient, build_supervisor_client


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


__all__ = ("KritaSupervisorClient", "build_krita_supervisor_client")
