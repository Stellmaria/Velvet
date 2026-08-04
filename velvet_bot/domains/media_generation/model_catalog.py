from __future__ import annotations

MODEL_DISPLAY_NAMES: dict[str, str] = {
    "nano_banana_2": "Nano Banana 2",
    "nano_banana_pro": "Nano Banana Pro",
    "seedream_5_pro": "Seedream 5 Pro",
    "wan_27_image": "Wan 2.7",
    "wan_27_image_pro": "Wan 2.7 Pro",
    "grok_imagine_video": "Grok Imagine v1",
    "grok_imagine_video_15": "Grok Imagine Video 1.5",
    "seedance_15_pro_video": "Seedance 1.5 Pro",
    "wan_26_image_to_video": "Wan 2.7",
}


def media_model_display_name(alias: object, *, fallback: str = "Генерация") -> str:
    normalized = str(alias or "").strip()
    return MODEL_DISPLAY_NAMES.get(normalized, normalized or fallback)


__all__ = ("MODEL_DISPLAY_NAMES", "media_model_display_name")
