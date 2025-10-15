import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import load_settings
from .cache import Cache
from .database import Database
from .utils.nanobanana import NanoBananaClient
from .middlewares.logging import SimpleLoggingMiddleware
from .middlewares.rate_limit import RateLimitMiddleware
from .handlers import start as start_handler
from .handlers import generate as generate_handler


async def main() -> None:
    settings = load_settings()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Shared services
    cache = Cache(settings.redis_url)
    db = Database(settings.supabase_url, settings.supabase_key)
    client = NanoBananaClient(
        base_url=settings.nanobanana_api_base,
        api_key=settings.nanobanana_api_key,
        timeout_seconds=settings.request_timeout_seconds,
    )

    # Middlewares
    dp.message.middleware(SimpleLoggingMiddleware())
    dp.message.middleware(RateLimitMiddleware(1.0))

    # Handlers setup
    start_handler.setup(db, cache)
    generate_handler.setup(client, db, cache)

    # Routers
    dp.include_router(start_handler.router)
    dp.include_router(generate_handler.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())