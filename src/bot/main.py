"""Bot entry point — dispatcher setup, router registration, polling."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.bot.middlewares import DbSessionMiddleware, RateLimitMiddleware
from src.handlers import admin, buy, keys, profile, start
from src.models.database import init_db
from src.utils.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # Middlewares
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(RateLimitMiddleware())

    # Routers — start.router last because it has the fallback message handler
    dp.include_router(buy.router)
    dp.include_router(keys.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    dp.include_router(start.router)

    # Start background notifier
    from src.services.notifier import run_notifier
    asyncio.create_task(run_notifier(bot))

    # Start trial HTTP server
    from src.web.trial import run_trial_server
    await run_trial_server()

    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        from src.services.xui_client import xui_client
        await xui_client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
