from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from velvet_bot.core.config.settings import parse_boolean, parse_bounded_integer


@dataclass(frozen=True, slots=True)
class RoleplaySettings:
    enabled: bool = False
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "R4C3R/qwen3-8b-heretic:q5_k_m"
    num_ctx: int = 8192
    max_output_tokens: int = 900
    temperature: float = 0.9
    top_p: float = 0.92
    min_p: float = 0.05
    repeat_penalty: float = 1.08
    keep_alive: str = "30m"
    summary_trigger_tokens: int = 5600
    recent_message_limit: int = 16
    timeout_seconds: int = 600


def _parse_float(
    value: str,
    *,
    variable_name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    cleaned = value.strip()
    if not cleaned:
        return default
    try:
        result = float(cleaned)
    except ValueError as error:
        raise RuntimeError(f"{variable_name} должен быть числом.") from error
    if not minimum <= result <= maximum:
        raise RuntimeError(
            f"{variable_name} должен быть от {minimum} до {maximum}."
        )
    return result


def load_roleplay_settings() -> RoleplaySettings:
    load_dotenv()

    provider = os.getenv("RP_PROVIDER", "ollama").strip().casefold()
    if provider != "ollama":
        raise RuntimeError("RP_PROVIDER пока поддерживает только ollama.")

    base_url = os.getenv(
        "RP_BASE_URL",
        "http://127.0.0.1:11434",
    ).strip().rstrip("/")
    if not base_url:
        raise RuntimeError("RP_BASE_URL не может быть пустым.")

    model = os.getenv(
        "RP_MODEL",
        "R4C3R/qwen3-8b-heretic:q5_k_m",
    ).strip()
    if not model:
        raise RuntimeError("RP_MODEL не может быть пустой.")

    num_ctx = parse_bounded_integer(
        os.getenv("RP_NUM_CTX", "8192"),
        variable_name="RP_NUM_CTX",
        default=8192,
        minimum=2048,
        maximum=32_768,
    )
    max_output_tokens = parse_bounded_integer(
        os.getenv("RP_MAX_OUTPUT_TOKENS", "900"),
        variable_name="RP_MAX_OUTPUT_TOKENS",
        default=900,
        minimum=128,
        maximum=4096,
    )
    if max_output_tokens >= num_ctx:
        raise RuntimeError("RP_MAX_OUTPUT_TOKENS должен быть меньше RP_NUM_CTX.")

    summary_trigger_tokens = parse_bounded_integer(
        os.getenv("RP_SUMMARY_TRIGGER_TOKENS", "5600"),
        variable_name="RP_SUMMARY_TRIGGER_TOKENS",
        default=5600,
        minimum=1024,
        maximum=30_000,
    )
    if summary_trigger_tokens >= num_ctx:
        raise RuntimeError(
            "RP_SUMMARY_TRIGGER_TOKENS должен быть меньше RP_NUM_CTX."
        )

    keep_alive = os.getenv("RP_KEEP_ALIVE", "30m").strip()[:40] or "30m"

    return RoleplaySettings(
        enabled=parse_boolean(
            os.getenv("RP_ENABLED", "false"),
            variable_name="RP_ENABLED",
        ),
        provider=provider,
        base_url=base_url,
        model=model,
        num_ctx=num_ctx,
        max_output_tokens=max_output_tokens,
        temperature=_parse_float(
            os.getenv("RP_TEMPERATURE", "0.9"),
            variable_name="RP_TEMPERATURE",
            default=0.9,
            minimum=0.0,
            maximum=2.0,
        ),
        top_p=_parse_float(
            os.getenv("RP_TOP_P", "0.92"),
            variable_name="RP_TOP_P",
            default=0.92,
            minimum=0.01,
            maximum=1.0,
        ),
        min_p=_parse_float(
            os.getenv("RP_MIN_P", "0.05"),
            variable_name="RP_MIN_P",
            default=0.05,
            minimum=0.0,
            maximum=1.0,
        ),
        repeat_penalty=_parse_float(
            os.getenv("RP_REPEAT_PENALTY", "1.08"),
            variable_name="RP_REPEAT_PENALTY",
            default=1.08,
            minimum=0.8,
            maximum=2.0,
        ),
        keep_alive=keep_alive,
        summary_trigger_tokens=summary_trigger_tokens,
        recent_message_limit=parse_bounded_integer(
            os.getenv("RP_RECENT_MESSAGE_LIMIT", "16"),
            variable_name="RP_RECENT_MESSAGE_LIMIT",
            default=16,
            minimum=4,
            maximum=80,
        ),
        timeout_seconds=parse_bounded_integer(
            os.getenv("RP_TIMEOUT_SECONDS", "600"),
            variable_name="RP_TIMEOUT_SECONDS",
            default=600,
            minimum=30,
            maximum=3600,
        ),
    )


__all__ = ("RoleplaySettings", "load_roleplay_settings")
