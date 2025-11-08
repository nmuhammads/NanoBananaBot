import logging
import asyncio
import hmac
import hashlib
import json
from fastapi import FastAPI, Request, Header, HTTPException

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update, BotCommand, BufferedInputFile, URLInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_settings
from .database import Database
from .cache import Cache
from .utils.nanobanana import NanoBananaClient
from .utils.i18n import t, normalize_lang
from .middlewares.logging import SimpleLoggingMiddleware
from .middlewares.rate_limit import RateLimitMiddleware
from .handlers import start as start_handler
from .handlers import generate as generate_handler
from .handlers import profile as profile_handler
from .handlers import topup as topup_handler
from .handlers import prices as prices_handler

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
cache = Cache(settings.redis_url)
client = NanoBananaClient(
    base_url=settings.nanobanana_api_base,
    api_key=settings.nanobanana_api_key,
    timeout_seconds=settings.request_timeout_seconds,
    callback_url=(settings.webhook_url.rstrip("/") + "/nb-callback") if settings.webhook_url else None,
)

# Middlewares
dp.message.middleware(SimpleLoggingMiddleware(logging.getLogger("nanobanana.middleware")))
dp.message.middleware(RateLimitMiddleware(1.0))
dp.callback_query.middleware(SimpleLoggingMiddleware(logging.getLogger("nanobanana.middleware")))
dp.callback_query.middleware(RateLimitMiddleware(1.0))

# Handlers setup
start_handler.setup(db)
generate_handler.setup(client, db, cache)
profile_handler.setup(db)
topup_handler.setup(db, settings)
prices_handler.setup(db)

# Routers
dp.include_router(start_handler.router)
dp.include_router(generate_handler.router)
dp.include_router(profile_handler.router)
dp.include_router(topup_handler.router)
dp.include_router(prices_handler.router)


app = FastAPI(title="NanoBananaBot Webhook")


async def _setup_webhook_with_retries(
    bot: Bot,
    url: str,
    secret_token: str | None,
    allowed_updates: list[str],
    timeout: float,
    attempts: int = 3,
    base_delay: float = 10.0,
) -> None:
    """Attempt to set webhook in the background with retries without blocking startup."""
    delay = base_delay
    for i in range(1, attempts + 1):
        try:
            await asyncio.wait_for(
                bot.set_webhook(
                    url=url,
                    secret_token=secret_token,
                    allowed_updates=allowed_updates,
                ),
                timeout=timeout,
            )
            logger.info("Webhook set on retry %s: %s", i, url)
            return
        except asyncio.TimeoutError:
            logger.warning("Retry %s timed out setting webhook", i)
        except asyncio.CancelledError:
            logger.warning("Retry %s cancelled while setting webhook", i)
        except Exception as e:
            logger.warning("Retry %s failed to set webhook: %s", i, e)
        try:
            await asyncio.sleep(delay)
        except Exception:
            pass
        delay *= 2
    logger.error("Exhausted webhook setup retries; continuing without webhook")


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
        await asyncio.wait_for(
            bot.delete_webhook(drop_pending_updates=True),
            timeout=settings.request_timeout_seconds,
        )
    except Exception as e:
        logger.warning("Failed to delete old webhook: %s", e)

    try:
        await asyncio.wait_for(
            bot.set_webhook(
                url=url,
                secret_token=settings.webhook_secret_token,
                allowed_updates=["message", "callback_query", "pre_checkout_query"],
            ),
            timeout=settings.request_timeout_seconds,
        )
        logger.info("Webhook set: %s, allowed=%s", url, ["message", "callback_query", "pre_checkout_query"])
    except asyncio.TimeoutError as e:
        logger.error("Timed out setting webhook within %ss; scheduling background retries", settings.request_timeout_seconds)
        try:
            asyncio.create_task(
                _setup_webhook_with_retries(
                    bot,
                    url,
                    settings.webhook_secret_token,
                    ["message", "callback_query", "pre_checkout_query"],
                    settings.request_timeout_seconds,
                )
            )
            logger.info("Webhook background retries scheduled")
        except Exception as sched_err:
            logger.warning("Failed to schedule webhook retries: %s", sched_err)
    except asyncio.CancelledError as e:
        logger.error("Webhook setup cancelled during startup; scheduling background retries")
        try:
            asyncio.create_task(
                _setup_webhook_with_retries(
                    bot,
                    url,
                    settings.webhook_secret_token,
                    ["message", "callback_query", "pre_checkout_query"],
                    settings.request_timeout_seconds,
                )
            )
            logger.info("Webhook background retries scheduled")
        except Exception as sched_err:
            logger.warning("Failed to schedule webhook retries: %s", sched_err)
    except Exception as e:
        logger.warning("Failed to set webhook: %s", e)
        try:
            asyncio.create_task(
                _setup_webhook_with_retries(
                    bot,
                    url,
                    settings.webhook_secret_token,
                    ["message", "callback_query", "pre_checkout_query"],
                    settings.request_timeout_seconds,
                )
            )
            logger.info("Webhook background retries scheduled")
        except Exception as sched_err:
            logger.warning("Failed to schedule webhook retries: %s", sched_err)

    # Register bot commands for user convenience
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Приветствие"),
            BotCommand(command="profile", description="Профиль и баланс"),
            BotCommand(command="generate", description="Генерация изображения"),
            BotCommand(command="topup", description="Пополнить баланс токенов"),
            BotCommand(command="prices", description="Цены на токены"),
            BotCommand(command="lang", description="Выбрать язык"),
            BotCommand(command="help", description="Список команд"),
        ])
    except Exception as e:
        logger.warning("Failed to set bot commands: %s", e)
    else:
        logger.info("Bot commands registered")

    # Debug info: configured Tribute products
    try:
        if settings.tribute_product_map:
            logger.info("Tribute products configured: %s", settings.tribute_product_map)
        else:
            logger.info("Tribute products configured: none")
    except Exception:
        logger.debug("Failed to log Tribute products config", exc_info=True)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    # Gracefully close external resources
    await bot.session.close()
    try:
        await cache.close()
    except Exception:
        pass


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

    # Идентификаторы могут быть добавлены в query параметрах callBackUrl
    try:
        qp = request.query_params
        qp_gen = qp.get("generationId")
        qp_user = qp.get("userId")
        if generation_id is None and qp_gen is not None:
            try:
                generation_id = int(qp_gen)
            except Exception:
                generation_id = qp_gen
        if user_id is None and qp_user is not None:
            try:
                user_id = int(qp_user)
            except Exception:
                user_id = qp_user
    except Exception:
        pass

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

    # Минимальная обработка ошибок: если провайдер вернул fail/неуспешный код, уведомим пользователя
    try:
        state_val = (data.get("data") or {}).get("state") or data.get("state")
        code_val = data.get("code")
        is_failed = (str(state_val).lower() in {"fail", "failed"}) or (isinstance(code_val, int) and code_val not in (200, 0))
    except Exception:
        is_failed = False

    if is_failed:
        fail_msg = ((data.get("data") or {}).get("failMsg")) or data.get("msg") or "Ошибка генерации"
        # Обновим статус генерации в базе, если есть id
        if generation_id is not None:
            try:
                await db.mark_generation_failed(int(generation_id), str(fail_msg))
            except Exception as e:
                logger.warning("Failed to mark generation failed id=%s: %s", generation_id, e)

        # Попробуем получить user_id из записи генерации, если он отсутствует
        if user_id is None and generation_id is not None:
            try:
                gen = db.client.table("generations").select("user_id").eq("id", int(generation_id)).limit(1).execute()
                rows = getattr(gen, "data", []) or []
                if rows:
                    user_id = rows[0].get("user_id")
            except Exception as e:
                logger.warning("Failed to fetch user_id for failed generation id=%s: %s", generation_id, e)

        # Вернём списанные токены (4) пользователю при неудачной генерации
        if user_id is not None:
            try:
                current_balance = await db.get_token_balance(int(user_id))
                new_balance = int(current_balance) + 4
                await db.set_token_balance(int(user_id), new_balance)
                logger.info("Refunded 4 tokens: user=%s balance %s->%s", user_id, current_balance, new_balance)
            except Exception as e:
                logger.warning("Failed to refund tokens to user %s: %s", user_id, e)

        # Уведомим пользователя о неудаче
        if user_id is not None:
            try:
                try:
                    res = db.client.table("users").select("language_code").eq("user_id", int(user_id)).limit(1).execute()
                    rows = getattr(res, "data", []) or []
                    lang = normalize_lang(rows[0].get("language_code") if rows else None)
                except Exception:
                    lang = "ru"

                reply_markup = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text=t(lang, "kb.repeat_generation"))],
                        [KeyboardButton(text=t(lang, "kb.new_generation")), KeyboardButton(text=t(lang, "kb.start"))],
                    ],
                    resize_keyboard=True,
                )
                # Добавим уведомление о возврате токенов
                refund_note = "Токены возвращены: +4" if lang == "ru" else "Tokens refunded: +4"
                await bot.send_message(chat_id=int(user_id), text=f"Ошибка генерации: {fail_msg}\n\n{refund_note}", reply_markup=reply_markup)
            except Exception as e:
                logger.warning("Failed to notify user %s of failure: %s", user_id, e)
        else:
            logger.info("Failure callback without user_id; marked generation failed")

        return {"ok": True}

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

        # If we have user_id, send image to the user chat as a document to preserve quality
        if user_id is not None:
            try:
                # Определим язык пользователя для подписи
                try:
                    res = db.client.table("users").select("language_code").eq("user_id", int(user_id)).limit(1).execute()
                    rows = getattr(res, "data", []) or []
                    lang = normalize_lang(rows[0].get("language_code") if rows else None)
                except Exception:
                    lang = "ru"
                # Отправим изображение как документ (URLInputFile) без изменения расширения
                from urllib.parse import urlparse
                filename = "image"
                try:
                    path = urlparse(str(image_url)).path
                    if path:
                        base = path.rsplit("/", 1)[-1]
                        if base:
                            filename = base
                except Exception:
                    pass

                try:
                    reply_markup = ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text=t(lang, "kb.repeat_generation"))],
                            [KeyboardButton(text=t(lang, "kb.new_generation")), KeyboardButton(text=t(lang, "kb.start"))],
                        ],
                        resize_keyboard=True,
                    )

                    file = URLInputFile(url=str(image_url), filename=filename)
                    await bot.send_document(chat_id=int(user_id), document=file, caption=t(lang, "gen.result_caption"), reply_markup=reply_markup)
                except Exception as e_doc:
                    logger.warning("Failed to send as document, fallback to photo: %s", e_doc)
                    await bot.send_photo(chat_id=int(user_id), photo=image_url, caption=t(lang, "gen.result_caption"), reply_markup=reply_markup)
            except Exception as e:
                logger.warning("Failed to send photo to user %s: %s", user_id, e)
        else:
            logger.info("Callback without user_id; image stored, no message sent")
    except Exception as e:
        logger.exception("Unhandled error in NanoBanana callback: %s", e)
        return {"ok": False}

    return {"ok": True}


@app.post("/tribute/webhook")
async def tribute_webhook(request: Request, trbt_signature: str | None = Header(default=None, alias="trbt-signature")) -> dict:
    """
    Tribute webhook for digital product purchases. Validates HMAC-SHA256 signature.
    Credits tokens to the user's balance based on configured product mapping.
    """
    if not settings.tribute_api_key:
        raise HTTPException(status_code=503, detail="Tribute integration not configured")

    raw = await request.body()
    calc = hmac.new(settings.tribute_api_key.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not trbt_signature or trbt_signature != calc:
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_name = (data.get("name") or data.get("event") or "").lower()
    payload = data.get("payload") or {}

    if event_name != "new_digital_product":
        logger.info("Ignored Tribute event: %s", event_name)
        return {"ok": True}

    product_id = payload.get("product_id") or payload.get("productId")
    tg_user_id = (
        payload.get("telegram_user_id")
        or payload.get("telegramUserId")
        or (payload.get("user") or {}).get("telegram_id")
        or (payload.get("user") or {}).get("telegramId")
    )

    if product_id is None or tg_user_id is None:
        logger.warning("Tribute webhook missing product_id or telegram_user_id: %s", data)
        return {"ok": False, "error": "missing fields"}

    # product_id can be a string slug or numeric; user id must be int
    product_id = str(product_id).strip()
    try:
        tg_user_id = int(tg_user_id)
    except Exception:
        logger.warning("Tribute webhook invalid telegram_user_id: tg=%s", tg_user_id)
        return {"ok": False, "error": "invalid ids"}

    # Build mapping of acceptable product identifiers -> token amounts
    # Each configured entry may be 'slug' or 'slug|numeric'. Accept slug, 'p'+slug and numeric id.
    tokens_by_pid: dict[str, int] = {}
    try:
        import re
        for tokens, raw in (settings.tribute_product_map or {}).items():
            value = str(raw).strip()
            parts = [p for p in re.split(r"[\|,:;/\s]+", value) if p]
            if not parts:
                continue
            slug = parts[0]
            # Add slug and 'p'+slug
            tokens_by_pid[slug] = int(tokens)
            if not slug.startswith("p"):
                tokens_by_pid["p" + slug] = int(tokens)
            # Add any numeric ids present
            for p in parts[1:]:
                if p.isdigit():
                    tokens_by_pid[p] = int(tokens)
    except Exception:
        # Fallback to direct mapping if splitting fails
        tokens_by_pid = {str(pid): int(tokens) for tokens, pid in settings.tribute_product_map.items()}

    tokens = tokens_by_pid.get(product_id)
    if not tokens:
        try:
            logger.warning("Unknown Tribute product_id=%s, known ids=%s", product_id, list(tokens_by_pid.keys()))
        except Exception:
            logger.warning("Unknown Tribute product_id=%s, no tokens credited", product_id)
        return {"ok": True}

    try:
        current = await db.get_token_balance(tg_user_id)
        new_balance = current + int(tokens)
        await db.set_token_balance(tg_user_id, new_balance)

        try:
            res = db.client.table("users").select("language_code").eq("user_id", tg_user_id).limit(1).execute()
            rows = getattr(res, "data", []) or []
            lang = normalize_lang(rows[0].get("language_code") if rows else None)
        except Exception:
            lang = "ru"
        await bot.send_message(chat_id=tg_user_id, text=t(lang, "topup.success", amount=int(tokens), balance=new_balance))
    except Exception as e:
        logger.exception("Failed to process Tribute webhook: %s", e)
        return {"ok": False}

    return {"ok": True}