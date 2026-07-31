from __future__ import annotations

import asyncio
import os


async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(64 * 1024):
            writer.write(chunk)
            await writer.drain()
    finally:
        try:
            writer.write_eof()
        except (AttributeError, OSError, RuntimeError):
            pass


async def _handle(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    socket_path = os.getenv(
        "SERVER_SUPERVISOR_SOCKET",
        "/runtime/supervisor/velvet-server-supervisor.sock",
    )
    try:
        upstream_reader, upstream_writer = await asyncio.open_unix_connection(
            socket_path
        )
    except OSError:
        client_writer.close()
        await client_writer.wait_closed()
        return
    try:
        await asyncio.gather(
            _pump(client_reader, upstream_writer),
            _pump(upstream_reader, client_writer),
        )
    finally:
        upstream_writer.close()
        client_writer.close()
        await asyncio.gather(
            upstream_writer.wait_closed(),
            client_writer.wait_closed(),
            return_exceptions=True,
        )


async def main() -> None:
    host = os.getenv("SERVER_SUPERVISOR_PROXY_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_SUPERVISOR_PROXY_PORT", "8765"))
    server = await asyncio.start_server(_handle, host, port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
