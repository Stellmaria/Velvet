from __future__ import annotations

import asyncio
import contextlib
import os


LISTEN_HOST = os.getenv("DB_PROXY_LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("DB_PROXY_LISTEN_PORT", "5432"))
UPSTREAM_HOST = os.getenv("DB_PROXY_UPSTREAM_HOST", "postgres")
UPSTREAM_PORT = int(os.getenv("DB_PROXY_UPSTREAM_PORT", "5432"))
CONNECT_TIMEOUT = float(os.getenv("DB_PROXY_CONNECT_TIMEOUT", "5"))
BUFFER_SIZE = 64 * 1024


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(BUFFER_SIZE):
            writer.write(data)
            await writer.drain()
    finally:
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()


async def _handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    try:
        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_connection(UPSTREAM_HOST, UPSTREAM_PORT),
            timeout=CONNECT_TIMEOUT,
        )
    except Exception:
        client_writer.close()
        with contextlib.suppress(Exception):
            await client_writer.wait_closed()
        return

    left = asyncio.create_task(_pipe(client_reader, upstream_writer))
    right = asyncio.create_task(_pipe(upstream_reader, client_writer))

    done, pending = await asyncio.wait(
        {left, right},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()

    for task in done | pending:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def main() -> None:
    server = await asyncio.start_server(
        _handle_client,
        LISTEN_HOST,
        LISTEN_PORT,
        reuse_address=True,
    )

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
