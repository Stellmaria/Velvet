from __future__ import annotations

import logging
import signal
import sys
import threading
from dataclasses import replace

from .codex_command import apply_codex_model, normalize_codex_command
from .config import SupervisorSettings
from .http_api import SupervisorHTTPServer
from .runtime import VelvetSupervisor


def configure_logging(settings: SupervisorSettings) -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                settings.logs_dir / "supervisor.log",
                encoding="utf-8",
            ),
        ],
    )


def main() -> int:
    loaded_settings = SupervisorSettings.load()
    model_command = apply_codex_model(
        loaded_settings.codex_command,
        loaded_settings.codex_model,
    )
    settings = replace(
        loaded_settings,
        codex_command=normalize_codex_command(model_command),
    )
    configure_logging(settings)
    logger = logging.getLogger(__name__)
    runtime = VelvetSupervisor(settings)
    server = SupervisorHTTPServer((settings.host, settings.port), runtime)
    stopped = threading.Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        logger.warning("Shutdown signal received: %s", signum)
        if stopped.is_set():
            return
        stopped.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        value = getattr(signal, signal_name, None)
        if value is not None:
            signal.signal(value, request_shutdown)

    runtime.start()
    logger.info(
        "Velvet Supervisor API listening on http://%s:%s",
        settings.host,
        settings.port,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        runtime.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
