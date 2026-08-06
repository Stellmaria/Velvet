from __future__ import annotations

import asyncio
import hashlib

import aiohttp

from velvet_bot.domains.telegram_storage.librarian_models import (
    LibrarianObject,
    StorageLibrarianError,
)


class ArthurStorageGatewayClient:
    def __init__(
        self,
        *,
        base_url: str,
        credential: str,
        timeout_seconds: int = 120,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._credential = credential
        self._timeout_seconds = max(5, int(timeout_seconds))

    async def health(self) -> bool:
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._base_url + "/health") as response:
                    return response.status == 200
        except (asyncio.TimeoutError, aiohttp.ClientError):
            return False

    async def download(
        self,
        item: LibrarianObject,
        *,
        max_bytes: int,
    ) -> bytes:
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        headers = {"Authorization": f"Bearer {self._credential}"}
        url = f"{self._base_url}/v1/storage/{item.object_id}"
        try:
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            ) as session:
                async with session.get(
                    url,
                    params={"max_bytes": str(int(max_bytes))},
                ) as response:
                    if response.status != 200:
                        message = (await response.text())[:500]
                        raise StorageLibrarianError(
                            f"Arthur Storage gateway HTTP {response.status}: {message}"
                        )
                    payload = await response.read()
        except StorageLibrarianError:
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError) as error:
            raise StorageLibrarianError(
                f"Arthur Storage gateway unavailable: {type(error).__name__}."
            ) from error

        if len(payload) != item.size_bytes:
            raise StorageLibrarianError(
                "Arthur Storage gateway returned an unexpected object size."
            )
        if hashlib.sha256(payload).hexdigest() != item.sha256:
            raise StorageLibrarianError(
                "Arthur Storage gateway returned an invalid object digest."
            )
        return payload


__all__ = ("ArthurStorageGatewayClient",)
