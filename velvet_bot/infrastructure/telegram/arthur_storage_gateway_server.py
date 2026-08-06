from __future__ import annotations

import hmac
import logging

from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from velvet_bot.core.config.arthur import ArthurStorageGatewaySettings
from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_models import (
    StorageLibrarianError,
    UnsupportedStorageContent,
)
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)
from velvet_bot.infrastructure.telegram.storage_librarian_files import (
    TelegramStorageObjectLoader,
)

logger = logging.getLogger(__name__)

_SETTINGS_KEY: web.AppKey[ArthurStorageGatewaySettings] = web.AppKey(
    "arthur_gateway_settings", ArthurStorageGatewaySettings
)
_DATABASE_KEY: web.AppKey[Database] = web.AppKey("arthur_gateway_database", Database)
_BOT_KEY: web.AppKey[Bot] = web.AppKey("arthur_gateway_bot", Bot)


@web.middleware
async def _authenticate(
    request: web.Request,
    handler: web.RequestHandler,
) -> web.StreamResponse:
    if request.path == "/health":
        return await handler(request)
    settings = request.app[_SETTINGS_KEY]
    supplied = request.headers.get("Authorization", "")
    expected = f"Bearer {settings.api_key}"
    if not hmac.compare_digest(supplied, expected):
        raise web.HTTPUnauthorized(text="unauthorized")
    return await handler(request)


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "arthur-storage-gateway"})


async def _download(request: web.Request) -> web.Response:
    settings = request.app[_SETTINGS_KEY]
    try:
        object_id = int(request.match_info["object_id"])
        requested_max = int(
            request.query.get("max_bytes", str(settings.max_object_bytes))
        )
    except ValueError as error:
        raise web.HTTPBadRequest(text="invalid object id or limit") from error
    if object_id <= 0 or requested_max <= 0:
        raise web.HTTPBadRequest(text="invalid object id or limit")
    max_bytes = min(requested_max, settings.max_object_bytes)

    repository = StorageLibrarianRepository(request.app[_DATABASE_KEY])
    item = await repository.load_object(object_id)
    if item is None:
        raise web.HTTPNotFound(text="storage object not found")

    loader = TelegramStorageObjectLoader(request.app[_BOT_KEY])
    try:
        payload = await loader.download(item, max_bytes=max_bytes)
    except UnsupportedStorageContent as error:
        raise web.HTTPForbidden(text="storage object is protected") from error
    except (StorageLibrarianError, TelegramAPIError) as error:
        logger.warning(
            "Arthur Storage gateway download failed object_id=%s error=%s",
            object_id,
            type(error).__name__,
        )
        raise web.HTTPBadGateway(text="storage object download failed") from error

    return web.Response(
        body=payload,
        content_type=item.mime_type or "application/octet-stream",
        headers={
            "X-Storage-Object-Id": str(item.object_id),
            "X-Storage-Sha256": item.sha256,
        },
    )


async def _startup(app: web.Application) -> None:
    settings = app[_SETTINGS_KEY]
    database = Database(settings.database_url)
    await database.initialize()
    app[_DATABASE_KEY] = database
    app[_BOT_KEY] = Bot(token=settings.velvet_bot_token)
    logger.info("Arthur Storage gateway initialized")


async def _cleanup(app: web.Application) -> None:
    bot = app.get(_BOT_KEY)
    if bot is not None:
        await bot.session.close()
    database = app.get(_DATABASE_KEY)
    if database is not None:
        await database.close()


def build_storage_gateway_app(
    settings: ArthurStorageGatewaySettings,
) -> web.Application:
    app = web.Application(
        middlewares=[_authenticate],
        client_max_size=1024,
    )
    app[_SETTINGS_KEY] = settings
    app.router.add_get("/health", _health)
    app.router.add_get("/v1/storage/{object_id:\\d+}", _download)
    app.on_startup.append(_startup)
    app.on_cleanup.append(_cleanup)
    return app


def run_storage_gateway() -> None:
    settings = ArthurStorageGatewaySettings.from_env()
    web.run_app(
        build_storage_gateway_app(settings),
        host=settings.host,
        port=settings.port,
        access_log=None,
    )


__all__ = ("build_storage_gateway_app", "run_storage_gateway")
