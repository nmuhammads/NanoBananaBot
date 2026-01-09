from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
    PreCheckoutQuery,
)

from ..database import Database
from ..utils.i18n import t, normalize_lang
from ..config import Settings
from ..utils.prices import RUBLE_PRICES, USD_PRICES, format_rubles, format_usd
from ..utils.hub import make_hub_link, ALLOWED_AMOUNTS, ALLOWED_STAR_AMOUNTS
import logging
import asyncio
import time
import re
import httpx


router = Router(name="topup")
_logger = logging.getLogger("seedream.topup")

_db: Database | None = None
_settings: Settings | None = None
_product_cache: dict[int, tuple[float, dict]] = {}


def setup(database: Database, settings: Settings | None = None) -> None:
    global _db, _settings
    _db = database
    if settings is not None:
        _settings = settings


def method_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "topup.method.sbp"), callback_data="topup_method:sbp")],
            [InlineKeyboardButton(text=t(lang, "topup.method.card"), callback_data="topup_method:card")],
            [InlineKeyboardButton(text=t(lang, "topup.method.old_stars"), callback_data="topup_method:invoice")],
            [InlineKeyboardButton(text=t(lang, "topup.method.bonus"), url="https://t.me/aiversebots?direct")],
        ]
    )


@router.message(Command("topup"))
async def topup(message: Message) -> None:
    assert _db is not None
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    balance = await _db.get_token_balance(message.from_user.id)
    await message.answer(
        (
            f"{t(lang, 'topup.title')}\n"
            f"{t(lang, 'topup.balance', balance=balance)}\n"
            f"{t(lang, 'topup.bonus_info')}\n\n"
            f"{t(lang, 'topup.method.title')}"
        ),
        reply_markup=method_keyboard(lang),
    )


@router.message((F.text == t("ru", "kb.topup")) | (F.text == t("en", "kb.topup")))
async def topup_text(message: Message) -> None:
    await topup(message)


async def _fetch_product(product_id: int) -> dict | None:
    if not _settings or not _settings.tribute_api_key:
        return None
    # Simple TTL cache (5 minutes)
    now = time.time()
    cached = _product_cache.get(product_id)
    if cached and (now - cached[0] < 300):
        return cached[1]
    try:
        timeout = _settings.request_timeout_seconds if _settings else 30
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(
                f"https://tribute.tg/api/v1/products/{product_id}",
                headers={
                    "X-Api-Key": _settings.tribute_api_key,
                    "Api-Key": _settings.tribute_api_key,
                    "Accept": "application/json",
                },
            )
            res.raise_for_status()
            data = res.json()
            _product_cache[product_id] = (now, data)
            return data
    except Exception:
        _logger.warning("Failed to fetch Tribute product id=%s", product_id, exc_info=True)
        return None


async def _packages_keyboard(lang: str, method: str) -> InlineKeyboardMarkup:
    # Deep links to hub @aiverse_hub_bot for SBP/Card/Stars
    def _norm(m: str) -> str:
        m = (m or "").strip().lower()
        if m in {"invoice", "stars", "xtr"}:  # treat invoice as stars
            return "stars"
        if m in {"sbp"}:
            return "sbp"
        if m in {"card"}:
            return "card"
        return m

    m = _norm(method)
    rows: list[list[InlineKeyboardButton]] = []
    # Stars now have their own allowed amounts list (in ✨),
    # SBP/Card keep existing token-based amounts
    allowed = ALLOWED_STAR_AMOUNTS if m == "stars" else ALLOWED_AMOUNTS
    for tokens in sorted(allowed):
        try:
            url = make_hub_link(m, tokens)
        except Exception:
            # Skip unsupported amounts/methods silently
            continue
        if m in {"sbp", "card"}:
            # Localized price label: RU → rubles, EN → dollars
            if lang.startswith("en"):
                usd = USD_PRICES.get(int(tokens))
                label = (
                    f"{tokens} Token" if usd is None else f"{tokens} Token ~ ${format_usd(usd)}"
                )
            else:
                rub = RUBLE_PRICES.get(int(tokens))
                label = (
                    f"{tokens} Токен" if rub is None else f"{tokens} Токен ~ {format_rubles(rub)} руб"
                )
        else:  # stars
            label = f"{tokens} ✨"
        rows.append([InlineKeyboardButton(text=label, url=url)])

    if not rows:
        rows = [[InlineKeyboardButton(text=t(lang, "topup.package.unavailable"), callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("topup_method:"))
async def choose_method(callback: CallbackQuery) -> None:
    assert _db is not None
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    method = (callback.data or "").split(":", 1)[1].strip().lower()
    try:
        _logger.info("topup_method selected: %s by user=%s", method, callback.from_user.id)
    except Exception:
        pass
    # For all methods (sbp, card, invoice/stars) show deep-link packages
    kb = await _packages_keyboard(lang, method)
    await callback.message.answer(
        f"{t(lang, 'topup.packages.title')}\n{t(lang, 'topup.link_hint')}",
        reply_markup=kb,
    )
    await callback.answer("OK")


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    try:
        await callback.answer("Оплата временно недоступна", show_alert=False)
    except Exception:
        pass


def topup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10 ✨", callback_data="topup_invoice:10"),
                InlineKeyboardButton(text="20 ✨", callback_data="topup_invoice:20"),
            ],
            [
                InlineKeyboardButton(text="30 ✨", callback_data="topup_invoice:30"),
                InlineKeyboardButton(text="50 ✨", callback_data="topup_invoice:50"),
            ],
            [
                InlineKeyboardButton(text="100 ✨", callback_data="topup_invoice:100"),
                InlineKeyboardButton(text="200 ✨", callback_data="topup_invoice:200"),
            ],
        ]
    )


async def _send_invoice(message: Message, amount: int) -> None:
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    # Stars conversion: 2 ✨ = 1 token. Display credited tokens in label/desc.
    credited_tokens = amount // 2
    prices = [LabeledPrice(label=t(lang, "topup.invoice_label", amount=credited_tokens), amount=amount)]
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title=t(lang, "topup.invoice_title"),
        description=t(lang, "topup.invoice_desc", amount=credited_tokens),
        payload=f"topup:{amount}",
        provider_token="",  # Stars для цифровых товаров — без провайдера
        currency="XTR",
        prices=prices,
        start_parameter=f"topup_{amount}",
    )


@router.callback_query(F.data.startswith("topup_invoice:"))
async def choose_invoice_topup(callback: CallbackQuery) -> None:
    data = callback.data or ""
    try:
        amount = int(data.split(":", 1)[1])
    except Exception:
        user = await _db.get_user(callback.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
        await callback.answer(t(lang, "topup.invalid_amount"), show_alert=True)
        return

    try:
        user = await _db.get_user(callback.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
        await callback.message.answer(t(lang, "topup.prepare", amount=amount))
        await _send_invoice(callback.message, amount)
        await callback.answer("OK")
    except Exception as e:
        _logger.exception("Failed to send Stars invoice: %s", e)
        user = await _db.get_user(callback.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
        await callback.answer(t(lang, "topup.invoice_fail"), show_alert=True)
        await callback.message.answer(t(lang, "topup.payment_unavailable"))


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    # Разрешаем оплату без дополнительных проверок
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    assert _db is not None
    sp = message.successful_payment
    if not sp or sp.currency != "XTR":
        user = await _db.get_user(message.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
        await message.answer(t(lang, "topup.currency_mismatch"))
        return

    amount = int(sp.total_amount)
    # 2 ✨ = 1 token
    credited_tokens = amount // 2
    current = await _db.get_token_balance(message.from_user.id)
    new_balance = current + credited_tokens
    await _db.set_token_balance(message.from_user.id, new_balance)

    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    await message.answer(t(lang, "topup.success", amount=credited_tokens, balance=new_balance))