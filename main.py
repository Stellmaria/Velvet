import asyncio
import logging

from velvet_bot.ai_model_routing import install_ai_model_routing
from velvet_bot.app import run_application


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    install_ai_model_routing()
    asyncio.run(run_application())
