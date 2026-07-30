from __future__ import annotations

import hmac
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiohttp import web

from velvet_bot.domains.watermark import WatermarkRepository
from velvet_bot.domains.watermark.models import WatermarkWorkItem
from velvet_bot.domains.watermark.remote_worker import KritaRemoteRepository
from velvet_bot.domains.watermark.service import WatermarkService
from velvet_bot.infrastructure.krita_bridge import KritaBridge

logger = logging.getLogger(__name__)
_WORKER_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "true" if default else "false").strip().casefold()
    if value in {"1", "true", "yes", "on", "да"}:
        return True
    if value in {"0", "false", "no", "off", "нет", ""}:
        return False
    raise RuntimeError(f"{name} должен быть true/false.")


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} должен быть целым числом.") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} должен быть от {minimum} до {maximum}.")
    return value


@dataclass(frozen=True, slots=True)
class KritaRemoteSettings:
    enabled: bool
    host: str
    port: int
    token: str | None
    lease_seconds: int
    max_upload_bytes: int

    @classmethod
    def from_env(cls) -> "KritaRemoteSettings":
        enabled = _env_bool("KRITA_REMOTE_WORKER_ENABLED")
        token = os.getenv("KRITA_REMOTE_WORKER_TOKEN", "").strip() or None
        if enabled and (token is None or len(token) < 32):
            raise RuntimeError(
                "KRITA_REMOTE_WORKER_ENABLED=true требует случайный "
                "KRITA_REMOTE_WORKER_TOKEN длиной не менее 32 символов."
            )
        return cls(
            enabled=enabled,
            host=os.getenv("KRITA_REMOTE_BIND_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_env_int("KRITA_REMOTE_PORT", 8766, minimum=1024, maximum=65535),
            token=token,
            lease_seconds=_env_int(
                "KRITA_REMOTE_LEASE_SECONDS", 180, minimum=30, maximum=3600
            ),
            max_upload_bytes=_env_int(
                "KRITA_REMOTE_MAX_UPLOAD_BYTES",
                50 * 1024 * 1024,
                minimum=1024 * 1024,
                maximum=200 * 1024 * 1024,
            ),
        )


class RemoteWatermarkService(WatermarkService):
    """Complete remote results without claiming jobs for a local Krita process."""

    def __init__(
        self,
        *,
        remote_repository: KritaRemoteRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._remote_repository = remote_repository

    async def process_once(self) -> int:
        processed = await self._remote_repository.requeue_expired(limit=100)
        for item in await self._repository.list_processing(limit=20):
            if not item.revision.response_path:
                continue
            try:
                payload = self._bridge.read_response(item.revision.response_path)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                await self._mark_recovery_error(item, f"Некорректный response Krita: {error}")
                processed += 1
                continue
            if payload is not None and await self._complete_if_ready(item):
                processed += 1
        return processed


class KritaRemoteCoordinator:
    def __init__(
        self,
        *,
        repository: WatermarkRepository,
        remote_repository: KritaRemoteRepository,
        bridge: KritaBridge,
        settings: KritaRemoteSettings,
    ) -> None:
        self._repository = repository
        self._remote_repository = remote_repository
        self._bridge = bridge
        self._settings = settings

    async def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        worker_id = self._worker_id(payload)
        await self._remote_repository.heartbeat_worker(
            worker_id=worker_id,
            version=self._optional_text(payload.get("version"), 128),
            hostname=self._optional_text(payload.get("hostname"), 255),
            active_job_id=self._optional_int(payload.get("active_job_id")),
            active_revision=self._optional_int(payload.get("active_revision")),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        return {"ok": True, "worker_id": worker_id}

    async def claim(self, payload: dict[str, Any]) -> dict[str, Any]:
        worker_id = self._worker_id(payload)
        await self._remote_repository.requeue_expired(limit=100)
        await self._remote_repository.heartbeat_worker(
            worker_id=worker_id,
            version=self._optional_text(payload.get("version"), 128),
            hostname=self._optional_text(payload.get("hostname"), 255),
        )
        lease = await self._remote_repository.claim(
            worker_id=worker_id,
            lease_seconds=self._settings.lease_seconds,
        )
        if lease is None:
            return {"ok": True, "job": None}
        item = await self._repository.get_current(lease.job_id)
        if item is None or item.revision.revision != lease.revision:
            await self._remote_repository.fail(
                job_id=lease.job_id,
                revision=lease.revision,
                worker_id=worker_id,
                token=lease.token,
                error="Текущая revision изменилась во время remote claim.",
            )
            return {"ok": True, "job": None}
        request_path, output_path, response_path = self._bridge.dispatch(item)
        await self._repository.set_dispatched_paths(
            job_id=item.job.id,
            revision=item.revision.revision,
            request_path=str(request_path),
            output_path=str(output_path),
            response_path=str(response_path),
        )
        await self._remote_repository.heartbeat_worker(
            worker_id=worker_id,
            version=self._optional_text(payload.get("version"), 128),
            hostname=self._optional_text(payload.get("hostname"), 255),
            active_job_id=item.job.id,
            active_revision=item.revision.revision,
        )
        base = f"/v1/krita/jobs/{item.job.id}/{item.revision.revision}"
        return {
            "ok": True,
            "job": {
                "job_id": item.job.id,
                "revision": item.revision.revision,
                "lease_token": lease.token,
                "lease_expires_at": lease.expires_at.isoformat(),
                "source_name": Path(item.job.source_path).name,
                "source_url": f"{base}/source",
                "logo": {
                    "kind": item.job.logo_kind,
                    "name": item.job.logo_name,
                    "width": item.job.logo_width,
                    "height": item.job.logo_height,
                    "url": f"{base}/logo" if item.job.logo_kind != "builtin" else None,
                },
                "remove_only": not item.revision.settings.enabled,
                "settings": {
                    "position": item.revision.settings.position,
                    "color": item.revision.settings.color,
                    "opacity": item.revision.settings.opacity,
                    "size": item.revision.settings.size,
                    "margin": item.revision.settings.margin,
                    "lock": item.revision.settings.lock,
                },
            },
        }

    async def item_for_lease(
        self,
        *,
        job_id: int,
        revision: int,
        worker_id: str,
        lease_token: str,
    ) -> WatermarkWorkItem:
        valid = await self._remote_repository.validate_lease(
            job_id=job_id,
            revision=revision,
            worker_id=worker_id,
            token=lease_token,
        )
        if not valid:
            raise web.HTTPConflict(text="Krita lease недействителен или истёк.")
        item = await self._repository.get_current(job_id)
        if item is None or item.revision.revision != revision:
            raise web.HTTPConflict(text="Krita revision больше не является текущей.")
        return item

    async def heartbeat_job(
        self,
        *,
        job_id: int,
        revision: int,
        worker_id: str,
        lease_token: str,
    ) -> dict[str, Any]:
        expires_at = await self._remote_repository.heartbeat_lease(
            job_id=job_id,
            revision=revision,
            worker_id=worker_id,
            token=lease_token,
            lease_seconds=self._settings.lease_seconds,
        )
        if expires_at is None:
            raise web.HTTPConflict(text="Krita lease недействителен или истёк.")
        await self._remote_repository.heartbeat_worker(
            worker_id=worker_id,
            version=None,
            hostname=None,
            active_job_id=job_id,
            active_revision=revision,
        )
        return {"ok": True, "lease_expires_at": expires_at.isoformat()}

    async def accept_result(
        self,
        *,
        job_id: int,
        revision: int,
        worker_id: str,
        lease_token: str,
        body: bytes,
    ) -> dict[str, Any]:
        item = await self.item_for_lease(
            job_id=job_id,
            revision=revision,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        if len(body) > self._settings.max_upload_bytes:
            raise web.HTTPRequestEntityTooLarge(
                max_size=self._settings.max_upload_bytes,
                actual_size=len(body),
            )
        if not body.startswith(b"\x89PNG\r\n\x1a\n"):
            raise web.HTTPBadRequest(text="Krita worker должен загрузить PNG.")
        if not item.revision.output_path or not item.revision.response_path:
            raise web.HTTPConflict(text="Серверные output paths не подготовлены.")
        output_path = self._bridge.validate_response_output(
            item.revision.output_path,
            expected_path=item.revision.output_path,
        )
        temporary = output_path.with_suffix(".png.uploading")
        temporary.write_bytes(body)
        os.replace(temporary, output_path)
        response_path = self._bridge.paths.ensure_in(
            item.revision.response_path,
            self._bridge.paths.responses,
        )
        response = {
            "status": "ok",
            "job_id": job_id,
            "revision": revision,
            "output_path": str(output_path),
            "remote_worker_id": worker_id,
        }
        temp_response = response_path.with_suffix(".json.tmp")
        temp_response.write_text(
            json.dumps(response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_response, response_path)
        await self._remote_repository.clear_worker_activity(worker_id=worker_id)
        return {"ok": True}

    async def fail_job(
        self,
        *,
        job_id: int,
        revision: int,
        worker_id: str,
        lease_token: str,
        error: str,
    ) -> dict[str, Any]:
        updated = await self._remote_repository.fail(
            job_id=job_id,
            revision=revision,
            worker_id=worker_id,
            token=lease_token,
            error=error or "Krita worker вернул ошибку.",
        )
        if not updated:
            raise web.HTTPConflict(text="Krita lease недействителен или истёк.")
        await self._remote_repository.clear_worker_activity(worker_id=worker_id)
        return {"ok": True}

    @staticmethod
    def _worker_id(payload: dict[str, Any]) -> str:
        worker_id = str(payload.get("worker_id") or "").strip()
        if not _WORKER_ID.fullmatch(worker_id):
            raise web.HTTPBadRequest(text="Некорректный worker_id.")
        return worker_id

    @staticmethod
    def _optional_text(value: Any, limit: int) -> str | None:
        text = str(value or "").strip()
        return text[:limit] or None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise web.HTTPBadRequest(text="Некорректный числовой идентификатор.") from error


class KritaRemoteWorkerServer:
    def __init__(
        self,
        *,
        coordinator: KritaRemoteCoordinator,
        settings: KritaRemoteSettings,
    ) -> None:
        self._coordinator = coordinator
        self._settings = settings
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        if self._runner is not None or not self._settings.enabled:
            return
        app = web.Application(client_max_size=self._settings.max_upload_bytes)
        app.router.add_get("/health", self._health)
        app.router.add_post("/v1/krita/heartbeat", self._heartbeat)
        app.router.add_post("/v1/krita/jobs/claim", self._claim)
        app.router.add_get("/v1/krita/jobs/{job_id:\\d+}/{revision:\\d+}/source", self._source)
        app.router.add_get("/v1/krita/jobs/{job_id:\\d+}/{revision:\\d+}/logo", self._logo)
        app.router.add_post("/v1/krita/jobs/{job_id:\\d+}/{revision:\\d+}/heartbeat", self._job_heartbeat)
        app.router.add_put("/v1/krita/jobs/{job_id:\\d+}/{revision:\\d+}/result", self._result)
        app.router.add_post("/v1/krita/jobs/{job_id:\\d+}/{revision:\\d+}/fail", self._fail)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._settings.host, self._settings.port)
        await site.start()
        logger.info(
            "Krita remote worker API listening on %s:%s",
            self._settings.host,
            self._settings.port,
        )

    async def stop(self) -> None:
        runner, self._runner = self._runner, None
        if runner is not None:
            await runner.cleanup()

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "service": "krita-remote-worker"})

    async def _heartbeat(self, request: web.Request) -> web.Response:
        self._require_auth(request)
        return web.json_response(await self._coordinator.heartbeat(await request.json()))

    async def _claim(self, request: web.Request) -> web.Response:
        self._require_auth(request)
        return web.json_response(await self._coordinator.claim(await request.json()))

    async def _source(self, request: web.Request) -> web.StreamResponse:
        worker_id, lease = self._lease_headers(request)
        item = await self._coordinator.item_for_lease(
            job_id=int(request.match_info["job_id"]),
            revision=int(request.match_info["revision"]),
            worker_id=worker_id,
            lease_token=lease,
        )
        source = self._coordinator._bridge.paths.ensure_in(
            item.job.source_path,
            self._coordinator._bridge.paths.sources,
        )
        if not source.is_file():
            raise web.HTTPNotFound(text="Исходник watermark job не найден.")
        return web.FileResponse(source, headers={"X-Velvet-Filename": source.name})

    async def _logo(self, request: web.Request) -> web.StreamResponse:
        worker_id, lease = self._lease_headers(request)
        item = await self._coordinator.item_for_lease(
            job_id=int(request.match_info["job_id"]),
            revision=int(request.match_info["revision"]),
            worker_id=worker_id,
            lease_token=lease,
        )
        if item.job.logo_kind == "builtin" or not item.job.logo_path:
            raise web.HTTPNotFound(text="Для job используется встроенный логотип.")
        logo = self._coordinator._bridge.paths.ensure_in(
            item.job.logo_path,
            self._coordinator._bridge.paths.assets,
        )
        if not logo.is_file():
            raise web.HTTPNotFound(text="Snapshot логотипа не найден.")
        return web.FileResponse(logo, headers={"X-Velvet-Filename": logo.name})

    async def _job_heartbeat(self, request: web.Request) -> web.Response:
        self._require_auth(request)
        worker_id, lease = self._lease_headers(request)
        return web.json_response(
            await self._coordinator.heartbeat_job(
                job_id=int(request.match_info["job_id"]),
                revision=int(request.match_info["revision"]),
                worker_id=worker_id,
                lease_token=lease,
            )
        )

    async def _result(self, request: web.Request) -> web.Response:
        self._require_auth(request)
        worker_id, lease = self._lease_headers(request)
        body = await request.read()
        return web.json_response(
            await self._coordinator.accept_result(
                job_id=int(request.match_info["job_id"]),
                revision=int(request.match_info["revision"]),
                worker_id=worker_id,
                lease_token=lease,
                body=body,
            )
        )

    async def _fail(self, request: web.Request) -> web.Response:
        self._require_auth(request)
        worker_id, lease = self._lease_headers(request)
        payload = await request.json()
        return web.json_response(
            await self._coordinator.fail_job(
                job_id=int(request.match_info["job_id"]),
                revision=int(request.match_info["revision"]),
                worker_id=worker_id,
                lease_token=lease,
                error=str(payload.get("error") or "")[:2000],
            )
        )

    def _require_auth(self, request: web.Request) -> None:
        expected = self._settings.token or ""
        supplied = request.headers.get("Authorization", "")
        prefix = "Bearer "
        token = supplied[len(prefix):] if supplied.startswith(prefix) else ""
        if not expected or not hmac.compare_digest(token, expected):
            raise web.HTTPUnauthorized(text="Недействительный Krita worker token.")

    def _lease_headers(self, request: web.Request) -> tuple[str, str]:
        self._require_auth(request)
        worker_id = request.headers.get("X-Krita-Worker-ID", "").strip()
        lease = request.headers.get("X-Krita-Lease", "").strip()
        if not _WORKER_ID.fullmatch(worker_id) or not lease:
            raise web.HTTPBadRequest(text="Не заданы Krita worker/lease headers.")
        return worker_id, lease


__all__ = (
    "KritaRemoteCoordinator",
    "KritaRemoteSettings",
    "KritaRemoteWorkerServer",
    "RemoteWatermarkService",
)
