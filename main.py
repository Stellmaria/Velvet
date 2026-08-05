import asyncio
import logging

from velvet_bot.app.gpt_image_2_bootstrap import install_gpt_image_2_bootstrap

install_gpt_image_2_bootstrap()

from velvet_bot.app import run_application


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(run_application())
