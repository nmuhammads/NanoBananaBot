import logging
import asyncio
import hmac
import hashlib
import json
from fastapi import FastAPI, Request, Header, HTTPException

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update, BotCommand, BufferedInputFile, URLInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton
from aiogram.fsm.storage.memory import MemoryStorage

from .config import load_settings
from .database import Database
from .cache import Cache
from .utils.nanobanana import NanoBananaClient
from .utils.piapi import PiapiClient
from .utils.generation_service import GenerationService
from .utils.i18n import t, normalize_lang
from .utils.r2 import R2Client
from .middlewares.logging import SimpleLoggingMiddleware
from .middlewares.rate_limit import RateLimitMiddleware
from .handlers import start as start_handler
from .handlers import generate as generate_handler
from .handlers import profile as profile_handler
from .handlers import topup as topup_handler
from .handlers import prices as prices_handler
from .handlers import avatars as avatars_handler
from .handlers import fallback as fallback_handler

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
piapi_client = PiapiClient(
    api_key=settings.piapi_api_key,
    timeout_seconds=settings.request_timeout_seconds,
    callback_url=(settings.webhook_url.rstrip("/") + "/piapi-callback") if settings.webhook_url else None,
)
generation_service = GenerationService(
    kie_client=client,
    piapi_client=piapi_client,
    db=db,
)
r2_client = R2Client()

# Middlewares
dp.message.middleware(SimpleLoggingMiddleware(logging.getLogger("nanobanana.middleware")))
dp.message.middleware(RateLimitMiddleware(1.0))
dp.callback_query.middleware(SimpleLoggingMiddleware(logging.getLogger("nanobanana.middleware")))
dp.callback_query.middleware(RateLimitMiddleware(1.0))


def generation_id_copy_keyboard(lang: str | None, generation_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "gen.copy_id_button"),
                    copy_text=CopyTextButton(text=str(generation_id)),
                )
            ]
        ]
    )

# Handlers setup
start_handler.setup(db)
generate_handler.setup(client, db, cache, r2_client, generation_service)
profile_handler.setup(db)
topup_handler.setup(db, settings)
prices_handler.setup(db)
avatars_handler.setup(db)

# Routers
dp.include_router(start_handler.router)
dp.include_router(generate_handler.router)
dp.include_router(profile_handler.router)
dp.include_router(topup_handler.router)

dp.include_router(prices_handler.router)
dp.include_router(avatars_handler.router)
# Fallback router must be last
dp.include_router(fallback_handler.router)


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
    # Initialize async Supabase client
    await db.init()

    # Ensure webhook URL is provided for webhook mode
    if not settings.webhook_url:
        raise RuntimeError("WEBHOOK_URL is required for webhook mode (Railway)")

    base_url = settings.webhook_url.rstrip("/")
    path = settings.webhook_path
    url = f"{base_url}{path}"

    # Check current webhook first - only update if needed
    try:
        webhook_info = await asyncio.wait_for(
            bot.get_webhook_info(),
            timeout=settings.request_timeout_seconds,
        )
        current_url = webhook_info.url or ""
        if current_url == url:
            logger.info("Webhook already set correctly: %s, skipping setup", url)
            # Still register bot commands
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
                logger.info("Bot commands registered")
            except Exception as e:
                logger.warning("Failed to set bot commands: %s", e)
            # Log Tribute products config
            try:
                if settings.tribute_product_map:
                    logger.info("Tribute products configured: %s", settings.tribute_product_map)
                else:
                    logger.info("Tribute products configured: none")
            except Exception:
                logger.debug("Failed to log Tribute products config", exc_info=True)
            return  # Webhook already configured, skip re-setting
        else:
            logger.info("Webhook URL differs (current=%s, target=%s), updating...", current_url, url)
    except Exception as e:
        logger.warning("Failed to check current webhook: %s, proceeding with setup", e)

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
            BotCommand(command="avatars", description="Мои аватары"),
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
    data_obj = data.get("data") or {}
    logger.info(
        "NanoBanana callback received: %s",
        {
            "imageUrl": data.get("imageUrl"),
            "image_url": data.get("image_url"),
            "generationId": data.get("generationId") or data_obj.get("generationId"),
            "userId": data.get("userId") or data_obj.get("userId"),
            "taskId": data.get("taskId") or data_obj.get("taskId"),
            "code": data.get("code"),
            "state": data_obj.get("state") or data.get("state"),
            "msg": data.get("msg"),
            "failMsg": data_obj.get("failMsg"),
        },
    )

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
        tokens_required = 3
        if param_json:
            import json
            try:
                param_obj = json.loads(param_json)
                meta = param_obj.get("meta") or {}
                generation_id = generation_id or meta.get("generationId")
                user_id = user_id or meta.get("userId")
                try:
                    tokens_raw = meta.get("tokens")
                    if isinstance(tokens_raw, (int, str)):
                        tr = int(tokens_raw)
                        if tr > 0:
                            tokens_required = tr
                except Exception:
                    pass
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
        
        # --- AUTO RETRY LOGIC ---
        try:
            retry_count = 0
            if param_json:
                import json
                try:
                    param_obj = json.loads(param_json)
                    retry_count = int((param_obj.get("meta") or {}).get("retry_count", 0))
                except Exception:
                    pass
            
            is_internal_error = "internal error" in str(fail_msg).lower()
            err_code = (data.get("data") or {}).get("code") or data.get("code")
            
            if is_internal_error and err_code in (429, 501, 500, "429", "501", "500"):
                if retry_count < 1 and generation_id is not None and user_id is not None:
                    logger.info("Auto-retrying generation_id=%s for user=%s due to internal error (retry %s)", generation_id, user_id, retry_count + 1)
                    
                    async def do_retry():
                        import asyncio
                        await asyncio.sleep(5)
                        try:
                            gen = await db.get_generation(int(generation_id))
                            if not gen:
                                return
                            
                            prompt_with_meta = gen.get("prompt", "")
                            prompt = prompt_with_meta.split(" [type=")[0].strip()
                            db_model = gen.get("model")
                            model = "nano-banana-pro" if db_model == "nanobanana-pro" else "google/nano-banana"
                            
                            ratio_val = "auto"
                            import re
                            m = re.search(r"ratio=([^;\]]+)", prompt_with_meta)
                            if m:
                                ratio_val = m.group(1).strip()
                            
                            ratio_map = {
                                "1:1": "1:1",
                                "3:4": "3:4",
                                "4:3": "4:3",
                                "9:16": "9:16",
                                "16:9": "16:9",
                            }
                            image_size = ratio_map.get(ratio_val)
                            image_urls = gen.get("input_images", [])
                            
                            new_meta = {"generationId": generation_id, "userId": user_id, "tokens": tokens_required, "retry_count": retry_count + 1}
                            if model == "nano-banana-pro":
                                await generation_service.generate_pro(
                                    prompt=prompt,
                                    image_urls=image_urls or None,
                                    aspect_ratio=image_size,
                                    resolution="2K",
                                    meta=new_meta
                                )
                            else:
                                await client.generate_image(
                                    prompt=prompt,
                                    model=model,
                                    image_urls=image_urls or None,
                                    image_size=image_size,
                                    output_format="png",
                                    meta=new_meta
                                )
                        except Exception as e:
                            logger.exception("Failed to auto-retry generation: %s", e)
                            
                    import asyncio
                    asyncio.create_task(do_retry())
                    return {"ok": True}
        except Exception as e:
            logger.warning("Error in auto-retry logic: %s", e)
        # ------------------------
        # Обновим статус генерации в базе, если есть id
        if generation_id is not None:
            try:
                await db.mark_generation_failed(int(generation_id), str(fail_msg))
            except Exception as e:
                logger.warning("Failed to mark generation failed id=%s: %s", generation_id, e)

        # Попробуем получить user_id из записи генерации, если он отсутствует
        if user_id is None and generation_id is not None:
            try:
                user_id = await db.get_generation_user_id(int(generation_id))
            except Exception as e:
                logger.warning("Failed to fetch user_id for failed generation id=%s: %s", generation_id, e)

        # Вернём списанные токены пользователю при неудачной генерации
        if user_id is not None:
            try:
                current_balance = await db.get_token_balance(int(user_id))
                new_balance = int(current_balance) + int(tokens_required)
                await db.set_token_balance(int(user_id), new_balance)
                logger.info("Refunded %s tokens: user=%s balance %s->%s", tokens_required, user_id, current_balance, new_balance)
            except Exception as e:
                logger.warning("Failed to refund tokens to user %s: %s", user_id, e)

        # Уведомим пользователя о неудаче
        if user_id is not None:
            try:
                try:
                    lang = normalize_lang(await db.get_user_language(int(user_id)))
                except Exception:
                    lang = "ru"

                reply_markup = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text=t(lang, "kb.repeat_generation"))],
                        [KeyboardButton(text=t(lang, "kb.generate")), KeyboardButton(text=t(lang, "kb.nanobanana_pro"))],
                        [KeyboardButton(text=t(lang, "kb.profile")), KeyboardButton(text=t(lang, "avatars.btn_label")), KeyboardButton(text=t(lang, "kb.topup"))],
                    ],
                    resize_keyboard=True,
                )
                # Добавим уведомление о возврате токенов
                refund_note = (
                    f"Токены возвращены: +{tokens_required}" if lang == "ru" else f"Tokens refunded: +{tokens_required}"
                )
                
                is_moderation_error = False
                seedream_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔥 Попробовать Seedream 4.5", url="https://t.me/seedreameditbot")]
                ])

                if "nsfw" in str(fail_msg).lower():
                    result_msg = "🚫 Из-за политик разработчика Нейросети, модель отклонила генерацию. Попробуйте в другой крутой модели — Seedream 4.5 (рекомендуем для лучшего качества)"
                    is_moderation_error = True
                elif "sensitive" in str(fail_msg).lower() or "E005" in str(fail_msg):
                    result_msg = "🚫 Система модерации отклонила запрос. Ваш текст или изображение содержит чувствительный контент. Попробуйте в другой крутой модели — Seedream 4.5 (рекомендуем для лучшего качества)"
                    is_moderation_error = True
                else:
                    # Sanitize
                    sanitized = str(fail_msg).replace("KIE API error:", "").replace("KIE API", "").strip()
                    result_msg = f"Ошибка генерации: {sanitized}"

                await bot.send_message(
                    chat_id=int(user_id), 
                    text=f"{result_msg}\n\n{refund_note}", 
                    reply_markup=seedream_kb if is_moderation_error else reply_markup
                )
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
                    user_id = await db.get_generation_user_id(int(generation_id))
                except Exception as e:
                    logger.warning("Failed to fetch generation user_id id=%s: %s", generation_id, e)

        # If we have user_id, send image to the user chat as a document to preserve quality
        if user_id is not None:
            try:
                # Определим язык пользователя для подписи
                try:
                    lang = normalize_lang(await db.get_user_language(int(user_id)))
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
                            [KeyboardButton(text=t(lang, "kb.generate")), KeyboardButton(text=t(lang, "kb.nanobanana_pro"))],
                            [KeyboardButton(text=t(lang, "kb.profile")), KeyboardButton(text=t(lang, "avatars.btn_label")), KeyboardButton(text=t(lang, "kb.topup"))],
                        ],
                        resize_keyboard=True,
                    )
                    result_caption = (
                        t(lang, "gen.result_caption_with_id", generation_id=generation_id)
                        if generation_id is not None
                        else t(lang, "gen.result_caption")
                    )

                    file = URLInputFile(url=str(image_url), filename=filename)
                    await bot.send_document(chat_id=int(user_id), document=file, caption=result_caption, reply_markup=reply_markup)
                except Exception as e_doc:
                    logger.warning("Failed to send as document, fallback to photo: %s", e_doc)
                    await bot.send_photo(chat_id=int(user_id), photo=image_url, caption=result_caption, reply_markup=reply_markup)
                if generation_id is not None:
                    try:
                        await bot.send_message(
                            chat_id=int(user_id),
                            text=t(lang, "gen.generation_id", generation_id=generation_id),
                            reply_markup=generation_id_copy_keyboard(lang, generation_id),
                        )
                    except Exception as e_copy:
                        logger.warning("Failed to send copy-id button to user %s: %s", user_id, e_copy)
            except Exception as e:
                logger.warning("Failed to send photo to user %s: %s", user_id, e)
        else:
            logger.info("Callback without user_id; image stored, no message sent")
    except Exception as e:
        logger.exception("Unhandled error in NanoBanana callback: %s", e)
        return {"ok": False}

    return {"ok": True}


@app.post("/piapi-callback")
async def piapi_callback(request: Request) -> dict:
    """
    Callback endpoint for Piapi API to deliver generated images.
    Piapi sends task object directly: {task_id, status, output: {image_urls: [...]}, ...}
    """
    # Get raw body for debugging
    raw_body = await request.body()
    logger.info("Piapi callback raw body (first 500 chars): %s", raw_body[:500] if raw_body else b"EMPTY")
    
    try:
        import json as json_module
        data = json_module.loads(raw_body) if raw_body else {}
    except Exception as parse_err:
        logger.error("Piapi callback JSON parse error: %s", parse_err)
        return {"ok": False, "error": "invalid json"}
    
    logger.info("Piapi callback parsed: task_id=%s, status=%s, keys=%s", data.get("task_id"), data.get("status"), list(data.keys()))

    # Piapi wraps task object in {"timestamp": ..., "data": {...}}
    # Extract nested data if present
    task_data = data.get("data", data)  # Fallback to data itself if no "data" key
    
    logger.info("Piapi task_data: task_id=%s, status=%s", task_data.get("task_id"), task_data.get("status"))

    # Parse query params for generationId/userId
    generation_id = None
    user_id = None
    tokens_required = 3
    try:
        qp = request.query_params
        qp_gen = qp.get("generationId")
        qp_user = qp.get("userId")
        if qp_gen:
            try:
                generation_id = int(qp_gen)
            except Exception:
                generation_id = qp_gen
        if qp_user:
            try:
                user_id = int(qp_user)
            except Exception:
                user_id = qp_user
    except Exception:
        pass

    # Check for status field from task_data
    status = str(task_data.get("status", "")).lower()
    
    if status == "completed":
        output = task_data.get("output", {})
        image_url = output.get("image_url")
        
        if not image_url:
            # Try alternative output formats
            image_urls = output.get("image_urls") or []
            if image_urls:
                image_url = image_urls[0]
        
        if not image_url:
            logger.warning("Piapi callback completed but no image_url: %s", data)
            return {"ok": False, "error": "missing image_url"}
        
        # Mark generation as completed
        if generation_id:
            try:
                await db.mark_generation_completed(int(generation_id), image_url)
                await db.update_generation_provider(int(generation_id), "piapi")
            except Exception as e:
                logger.warning("Failed to mark generation completed: %s", e)
        
        # Fetch user_id from generation if not provided
        if user_id is None and generation_id:
            try:
                user_id = await db.get_generation_user_id(int(generation_id))
            except Exception as e:
                logger.warning("Failed to fetch user_id: %s", e)
        
        # Send image to user
        if user_id:
            try:
                # Get user language
                try:
                    lang = normalize_lang(await db.get_user_language(int(user_id)))
                except Exception:
                    lang = "ru"
                
                reply_markup = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text=t(lang, "kb.repeat_generation"))],
                        [KeyboardButton(text=t(lang, "kb.generate")), KeyboardButton(text=t(lang, "kb.nanobanana_pro"))],
                        [KeyboardButton(text=t(lang, "kb.profile")), KeyboardButton(text=t(lang, "avatars.btn_label")), KeyboardButton(text=t(lang, "kb.topup"))],
                    ],
                    resize_keyboard=True,
                )
                
                # Extract filename from URL
                from urllib.parse import urlparse
                filename = "image.png"
                try:
                    path = urlparse(str(image_url)).path
                    if path:
                        base = path.rsplit("/", 1)[-1]
                        if base:
                            filename = base
                except Exception:
                    pass
                result_caption = (
                    t(lang, "gen.result_caption_with_id", generation_id=generation_id)
                    if generation_id is not None
                    else t(lang, "gen.result_caption")
                )
                
                try:
                    file = URLInputFile(url=str(image_url), filename=filename)
                    await bot.send_document(chat_id=int(user_id), document=file, caption=result_caption, reply_markup=reply_markup)
                except Exception as e_doc:
                    logger.warning("Piapi: Failed to send as document: %s", e_doc)
                    await bot.send_photo(chat_id=int(user_id), photo=image_url, caption=result_caption, reply_markup=reply_markup)
                if generation_id is not None:
                    try:
                        await bot.send_message(
                            chat_id=int(user_id),
                            text=t(lang, "gen.generation_id", generation_id=generation_id),
                            reply_markup=generation_id_copy_keyboard(lang, generation_id),
                        )
                    except Exception as e_copy:
                        logger.warning("Piapi: Failed to send copy-id button to user %s: %s", user_id, e_copy)
            except Exception as e:
                logger.warning("Failed to send photo to user %s: %s", user_id, e)
        
        return {"ok": True}
    
    # Handle failure
    if status == "failed":
        error = task_data.get("error", {})
        fail_msg = error.get("message") or error.get("raw_message") or "Piapi generation failed"
        
        # Mark generation failed
        if generation_id:
            try:
                await db.mark_generation_failed(int(generation_id), str(fail_msg))
            except Exception as e:
                logger.warning("Failed to mark generation failed: %s", e)
        
        # Fetch user_id if needed
        if user_id is None and generation_id:
            try:
                user_id = await db.get_generation_user_id(int(generation_id))
            except Exception:
                pass
        
        # Refund tokens and notify user
        if user_id:
            try:
                current = await db.get_token_balance(int(user_id))
                new_balance = current + tokens_required
                await db.set_token_balance(int(user_id), new_balance)
                logger.info("Refunded %s tokens: user=%s", tokens_required, user_id)
            except Exception as e:
                logger.warning("Failed to refund tokens: %s", e)
            
            try:
                try:
                    lang = normalize_lang(await db.get_user_language(int(user_id)))
                except Exception:
                    lang = "ru"
                
                reply_markup = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text=t(lang, "kb.repeat_generation"))],
                        [KeyboardButton(text=t(lang, "kb.generate")), KeyboardButton(text=t(lang, "kb.nanobanana_pro"))],
                        [KeyboardButton(text=t(lang, "kb.profile")), KeyboardButton(text=t(lang, "avatars.btn_label")), KeyboardButton(text=t(lang, "kb.topup"))],
                    ],
                    resize_keyboard=True,
                )
                
                refund_note = f"Токены возвращены: +{tokens_required}" if lang == "ru" else f"Tokens refunded: +{tokens_required}"
                await bot.send_message(
                    chat_id=int(user_id),
                    text=f"Ошибка генерации: {fail_msg}\n\n{refund_note}",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.warning("Failed to notify user of failure: %s", e)
        
        return {"ok": True}
    
    # Still processing
    logger.info("Piapi callback status: %s (task still processing)", status)
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
            lang = normalize_lang(await db.get_user_language(tg_user_id))
        except Exception:
            lang = "ru"
        await bot.send_message(chat_id=tg_user_id, text=t(lang, "topup.success", amount=int(tokens), balance=new_balance))
    except Exception as e:
        logger.exception("Failed to process Tribute webhook: %s", e)
        return {"ok": False}

    return {"ok": True}
