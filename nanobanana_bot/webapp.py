import logging
from fastapi import FastAPI, Request, Header, HTTPException

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update, BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_settings
from .database import Database
from .utils.nanobanana import NanoBananaClient
from .middlewares.logging import SimpleLoggingMiddleware
from .middlewares.rate_limit import RateLimitMiddleware
from .handlers import start as start_handler
from .handlers import generate as generate_handler
from .handlers import profile as profile_handler


# Initialize settings and core bot components
settings = load_settings()

bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# Shared services
db = Database(settings.supabase_url, settings.supabase_key)
client = NanoBananaClient(
    base_url=settings.nanobanana_api_base,
    api_key=settings.nanobanana_api_key,
    timeout_seconds=settings.request_timeout_seconds,
)

# Middlewares
dp.message.middleware(SimpleLoggingMiddleware(logging.getLogger("nanobanana.middleware")))
dp.message.middleware(RateLimitMiddleware(1.0))

# Handlers setup
start_handler.setup(db)
generate_handler.setup(client, db)
profile_handler.setup(db)

# Routers
dp.include_router(start_handler.router)
dp.include_router(generate_handler.router)
dp.include_router(profile_handler.router)


app = FastAPI(title="NanoBananaBot Webhook")


@app.on_event("startup")
async def on_startup() -> None:
    # Ensure webhook URL is provided for webhook mode
    if not settings.webhook_url:
        raise RuntimeError("WEBHOOK_URL is required for webhook mode (Railway)")

    base_url = settings.webhook_url.rstrip("/")
    path = settings.webhook_path
    url = f"{base_url}{path}"

    # Reset previous webhook to avoid conflicts and drop pending updates
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.getLogger("nanobanana.middleware").warning("Failed to delete old webhook: %s", e)

    await bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret_token,
        allowed_updates=["message", "callback_query"],
    )

    # Register bot commands for user convenience
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Приветствие"),
            BotCommand(command="profile", description="Профиль и баланс"),
            BotCommand(command="generate", description="Генерация изображения"),
            BotCommand(command="help", description="Список команд"),
        ])
    except Exception as e:
        logging.getLogger("nanobanana.middleware").warning("Failed to set bot commands: %s", e)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    # Gracefully close external resources
    await bot.session.close()


@app.get("/")
async def health() -> dict:
    return {"status": "ok"}


@app.post(settings.webhook_path)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    # Optional verification of Telegram secret token
    if settings.webhook_secret_token and x_telegram_bot_api_secret_token != settings.webhook_secret_token:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    data = await request.json()
    update = Update.model_validate(data)
    try:
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.getLogger("nanobanana.middleware").exception("Unhandled error while processing update: %s", e)
        # Return ok to avoid Telegram retries storms; error is logged.
    return {"ok": True}