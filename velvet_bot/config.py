import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str


def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env "
            "и вставьте токен, полученный у @BotFather."
        )

    return Settings(bot_token=bot_token)
