from __future__ import annotations

import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from scripts.server_preflight import ValidationReport, _validate_krita_remote
from velvet_bot.infrastructure.krita_remote_api import (
    KritaRemoteSettings,
    KritaRemoteWorkerServer,
    _atomic_replace_bytes,
    _validate_png_structure,
)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _valid_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    raw = b"\x00\x00\x00\x00\x00"
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def _settings(*, public: bool = False, failure_limit: int = 2) -> KritaRemoteSettings:
    return KritaRemoteSettings(
        enabled=True,
        host="0.0.0.0" if public else "127.0.0.1",
        port=8766,
        token="x" * 32,
        lease_seconds=180,
        max_upload_bytes=1024 * 1024,
        allow_unsafe_public_bind=public,
        auth_failure_limit=failure_limit,
        auth_failure_window_seconds=60,
        auth_failure_cooldown_seconds=120,
        request_timeout_seconds=30,
        max_concurrent_uploads=1,
    )


class KritaRemoteSecurityTests(unittest.IsolatedAsyncioTestCase):
    def test_png_structure_validates_crc_and_terminal_chunk(self) -> None:
        payload = _valid_png()
        _validate_png_structure(payload)

        corrupted = bytearray(payload)
        corrupted[-1] ^= 0x01
        with self.assertRaises(web.HTTPBadRequest):
            _validate_png_structure(bytes(corrupted))
        with self.assertRaises(web.HTTPBadRequest):
            _validate_png_structure(payload[:-12])

    def test_atomic_replace_removes_staging_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "result.png"
            with patch(
                "velvet_bot.infrastructure.krita_remote_api.os.replace",
                side_effect=OSError("simulated"),
            ):
                with self.assertRaises(OSError):
                    _atomic_replace_bytes(destination, _valid_png())
            self.assertEqual([], list(Path(directory).glob("*.uploading")))
            self.assertFalse(destination.exists())

    def test_server_preflight_rejects_public_bind_without_override(self) -> None:
        report = ValidationReport()
        _validate_krita_remote(
            {
                "KRITA_WATERMARK_ENABLED": "true",
                "KRITA_REMOTE_WORKER_ENABLED": "true",
                "KRITA_REMOTE_WORKER_TOKEN": "x" * 32,
                "KRITA_REMOTE_BIND_HOST": "0.0.0.0",
                "KRITA_REMOTE_ALLOW_UNSAFE_PUBLIC_BIND": "false",
            },
            report,
        )
        self.assertFalse(report.ok)
        self.assertTrue(any("loopback" in item for item in report.errors))

    def test_server_preflight_accepts_loopback(self) -> None:
        report = ValidationReport()
        _validate_krita_remote(
            {
                "KRITA_WATERMARK_ENABLED": "true",
                "KRITA_REMOTE_WORKER_ENABLED": "true",
                "KRITA_REMOTE_WORKER_TOKEN": "x" * 32,
                "KRITA_REMOTE_BIND_HOST": "127.0.0.1",
            },
            report,
        )
        self.assertTrue(report.ok)
        self.assertTrue(any("loopback" in item for item in report.checks))

    async def test_public_health_requires_bearer_auth(self) -> None:
        server = KritaRemoteWorkerServer(coordinator=object(), settings=_settings(public=True))  # type: ignore[arg-type]
        request = make_mocked_request("GET", "/health")
        with self.assertRaises(web.HTTPUnauthorized):
            await server._health(request)

    def test_auth_failures_enter_cooldown_without_token_echo(self) -> None:
        server = KritaRemoteWorkerServer(coordinator=object(), settings=_settings())  # type: ignore[arg-type]
        request = make_mocked_request(
            "POST",
            "/v1/krita/jobs/claim",
            headers={"Authorization": "Bearer do-not-log-this-token"},
        )
        with self.assertLogs(
            "velvet_bot.infrastructure.krita_remote_api", level="WARNING"
        ) as captured:
            with self.assertRaises(web.HTTPUnauthorized):
                server._require_auth(request)
            with self.assertRaises(web.HTTPTooManyRequests):
                server._require_auth(request)
        rendered = "\n".join(captured.output)
        self.assertNotIn("do-not-log-this-token", rendered)
        self.assertIn("client=", rendered)

    async def test_upload_headers_require_png_and_exact_length(self) -> None:
        server = KritaRemoteWorkerServer(coordinator=object(), settings=_settings())  # type: ignore[arg-type]
        request = make_mocked_request(
            "PUT",
            "/v1/krita/jobs/1/1/result",
            headers={
                "Authorization": "Bearer " + "x" * 32,
                "X-Krita-Worker-ID": "worker-1",
                "X-Krita-Lease": "lease",
                "Content-Type": "application/octet-stream",
                "Content-Length": "10",
            },
            match_info={"job_id": "1", "revision": "1"},
        )
        with self.assertRaises(web.HTTPUnsupportedMediaType):
            await server._result(request)

        request = make_mocked_request(
            "PUT",
            "/v1/krita/jobs/1/1/result",
            headers={
                "Authorization": "Bearer " + "x" * 32,
                "X-Krita-Worker-ID": "worker-1",
                "X-Krita-Lease": "lease",
                "Content-Type": "image/png",
            },
            match_info={"job_id": "1", "revision": "1"},
        )
        with self.assertRaises(web.HTTPLengthRequired):
            await server._result(request)

    def test_settings_reject_public_bind_even_when_remote_disabled(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KRITA_REMOTE_WORKER_ENABLED": "false",
                "KRITA_REMOTE_BIND_HOST": "192.0.2.10",
                "KRITA_REMOTE_ALLOW_UNSAFE_PUBLIC_BIND": "false",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                KritaRemoteSettings.from_env()


if __name__ == "__main__":
    unittest.main()
