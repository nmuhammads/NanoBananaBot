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
from .handlers import topup as topup_handler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("nanobanana.app")


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
    callback_url=(settings.webhook_url.rstrip("/") + "/nb-callback") if settings.webhook_url else None,
)

# Middlewares
dp.message.middleware(SimpleLoggingMiddleware(logging.getLogger("nanobanana.middleware")))
dp.message.middleware(RateLimitMiddleware(1.0))

# Handlers setup
start_handler.setup(db)
generate_handler.setup(client, db)
profile_handler.setup(db)
topup_handler.setup(db)

# Routers
dp.include_router(start_handler.router)
dp.include_router(generate_handler.router)
dp.include_router(profile_handler.router)
dp.include_router(topup_handler.router)


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
        logger.warning("Failed to delete old webhook: %s", e)

    await bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret_token,
        allowed_updates=["message", "callback_query", "pre_checkout_query"],
    )
    logger.info("Webhook set: %s, allowed=%s", url, ["message", "callback_query", "pre_checkout_query"])

    # Register bot commands for user convenience
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Приветствие"),
            BotCommand(command="profile", description="Профиль и баланс"),
            BotCommand(command="generate", description="Генерация изображения"),
            BotCommand(command="topup", description="Пополнить баланс токенов"),
            BotCommand(command="help", description="Список команд"),
        ])
    except Exception as e:
        logger.warning("Failed to set bot commands: %s", e)
    else:
        logger.info("Bot commands registered")


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
    logger.debug("Incoming update JSON: %s", data)
    update = Update.model_validate(data)
    try:
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.exception("Unhandled error while processing update: %s", e)
        # Return ok to avoid Telegram retries storms; error is logged.
    return {"ok": True}


@app.post("/nb-callback")
async def nanobanana_callback(request: Request) -> dict:
    """
    Callback endpoint for NanoBanana API to deliver generated images.
    Expected JSON may include keys like: imageUrl/image_url, generationId, userId, taskId.
    """
    data = await request.json()
    logger.info("NanoBanana callback received: %s", {k: data.get(k) for k in ["imageUrl", "image_url", "generationId", "userId", "taskId"]})

    # KIE format: top-level {code,msg,data}, where data.resultJson is a JSON string with resultUrls[]
    # and data.param is a JSON string that contains meta.generationId/userId.
    image_url = data.get("imageUrl") or data.get("image_url") or (data.get("data") or {}).get("imageUrl")
    generation_id = data.get("generationId") or (data.get("data") or {}).get("generationId")
    user_id = data.get("userId") or (data.get("data") or {}).get("userId")

    try:
        payload_data = data.get("data") or {}
        # Parse resultJson if present
        result_json = payload_data.get("resultJson")
        if result_json and not image_url:
            import json
            try:
                result_obj = json.loads(result_json)
                urls = result_obj.get("resultUrls") or []
                if isinstance(urls, list) and urls:
                    image_url = urls[0]
            except Exception as e:
                logger.warning("Failed to parse resultJson: %s", e)

        # Parse param.meta for generationId/userId if missing
        param_json = payload_data.get("param")
        if param_json and (generation_id is None or user_id is None):
            import json
            try:
                param_obj = json.loads(param_json)
                meta = param_obj.get("meta") or {}
                generation_id = generation_id or meta.get("generationId")
                user_id = user_id or meta.get("userId")
            except Exception as e:
                logger.warning("Failed to parse param meta: %s", e)
    except Exception as e:
        logger.warning("General parsing error for KIE callback: %s", e)

    if not image_url:
        logger.warning("NanoBanana callback missing image url after parsing: %s", data)
        return {"ok": False, "error": "missing image url"}

    try:
        # If we have generation_id, update Supabase and fetch user_id when needed
        if generation_id is not None:
            try:
                await db.mark_generation_completed(int(generation_id), image_url)
            except Exception as e:
                logger.warning("Failed to mark generation completed id=%s: %s", generation_id, e)

            # If user_id absent, try to fetch from generation record
            if user_id is None:
                try:
                    # Lazy import to avoid circular
                    from .database import Database  # already imported above
                    # Use internal client to query
                    gen = db.client.table("generations").select("user_id").eq("id", int(generation_id)).limit(1).execute()
                    rows = getattr(gen, "data", []) or []
                    if rows:
                        user_id = rows[0].get("user_id")
                except Exception as e:
                    logger.warning("Failed to fetch generation user_id id=%s: %s", generation_id, e)

        # If we have user_id, send photo to the user chat
        if user_id is not None:
            try:
                await bot.send_photo(chat_id=int(user_id), photo=image_url, caption="Результат генерации")
            except Exception as e:
                logger.warning("Failed to send photo to user %s: %s", user_id, e)
        else:
            logger.info("Callback without user_id; image stored, no message sent")
    except Exception as e:
        logger.exception("Unhandled error in NanoBanana callback: %s", e)
        return {"ok": False}

    return {"ok": True}