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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from ..database import Database
from ..utils.i18n import t, normalize_lang
from ..config import Settings
from ..utils.prices import (
    RUBLE_PRICES,
    USD_PRICES_CENTS,
    EUR_PRICES_CENTS,
    format_rubles,
    format_usd_cents,
    format_eur_cents,
    calculate_custom_price,
)
from ..utils.hub import (
    make_hub_link,
    ALLOWED_SBP_AMOUNTS,
    ALLOWED_STAR_AMOUNTS,
    MIN_CUSTOM_TOKENS,
    MAX_CUSTOM_TOKENS,
    is_valid_custom_tokens,
)
import logging


router = Router(name="topup")
_logger = logging.getLogger("nanobanana.topup")

_db: Database | None = None
_settings: Settings | None = None


class CardTopupStates(StatesGroup):
    waiting_amount = State()


def setup(database: Database, settings: Settings | None = None) -> None:
    global _db, _settings
    _db = database
    _settings = settings


def _get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database is not initialized")
    return _db


def _message_user_id(message: Message) -> int:
    if message.from_user is None:
        raise RuntimeError("Message user is unavailable")
    return message.from_user.id


def _message_lang_hint(message: Message) -> str | None:
    return message.from_user.language_code if message.from_user else None


def _callback_user_id(callback: CallbackQuery) -> int:
    if callback.from_user is None:
        raise RuntimeError("Callback user is unavailable")
    return callback.from_user.id


def _callback_lang_hint(callback: CallbackQuery) -> str | None:
    return callback.from_user.language_code if callback.from_user else None


def _callback_message(callback: CallbackQuery) -> Message:
    msg = callback.message
    if not isinstance(msg, Message):
        raise RuntimeError("Callback message is unavailable")
    return msg


def _topup_main_text(lang: str, balance: int) -> str:
    return (
        f"{t(lang, 'topup.title')}\n"
        f"{t(lang, 'topup.balance', balance=balance)}\n"
        f"{t(lang, 'topup.bonus_info')}\n\n"
        f"{t(lang, 'topup.method.title')}"
    )


def method_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "topup.method.sbp"), callback_data="topup_method:sbp")],
            [InlineKeyboardButton(text=t(lang, "topup.method.card"), callback_data="topup_method:card")],
            [InlineKeyboardButton(text=t(lang, "topup.method.old_stars"), callback_data="topup_method:invoice")],
            [InlineKeyboardButton(text=t(lang, "topup.method.bonus"), url="https://t.me/aiversebots?direct")],
        ]
    )


def _card_currency_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "topup.card_currency.rub"), callback_data="topup_card_currency:rub")],
            [InlineKeyboardButton(text=t(lang, "topup.card_currency.usd"), callback_data="topup_card_currency:usd")],
            [InlineKeyboardButton(text=t(lang, "topup.card_currency.eur"), callback_data="topup_card_currency:eur")],
            [InlineKeyboardButton(text=t(lang, "common.back"), callback_data="topup_method:menu")],
        ]
    )


def _card_amount_keyboard(lang: str, method: str) -> InlineKeyboardMarkup:
    currency = "rub"
    if "_" in method:
        currency = method.split("_", 1)[1]

    if currency == "usd":
        price_map = USD_PRICES_CENTS
    elif currency == "eur":
        price_map = EUR_PRICES_CENTS
    else:
        price_map = RUBLE_PRICES

    rows: list[list[InlineKeyboardButton]] = []
    package_buttons: list[InlineKeyboardButton] = []

    for tokens in sorted(price_map):
        try:
            url = make_hub_link(method, tokens)
        except Exception:
            continue
        price_display = _estimate_card_price(tokens, currency)
        package_buttons.append(InlineKeyboardButton(text=f"{tokens} • {price_display}", url=url))

    if not package_buttons:
        rows.append([InlineKeyboardButton(text=t(lang, "topup.package.unavailable"), callback_data="noop")])
    else:
        for i in range(0, len(package_buttons), 2):
            rows.append(package_buttons[i : i + 2])

    rows.append([InlineKeyboardButton(text=t(lang, "topup.custom_input"), callback_data=f"topup_custom:{method}")])
    rows.append([InlineKeyboardButton(text=t(lang, "topup.back_to_currency"), callback_data="topup_method:card")])
    rows.append([InlineKeyboardButton(text=t(lang, "common.back"), callback_data="topup_method:menu")])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def _payment_link_keyboard(lang: str, url: str, button_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=url)],
            [InlineKeyboardButton(text=t(lang, "common.back"), callback_data="topup_method:menu")],
        ]
    )


async def _safe_edit_text(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        msg = _callback_message(callback)
    except RuntimeError:
        return

    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        _logger.warning("edit_text failed, sending new message: %s", e)
        await msg.answer(text, reply_markup=reply_markup)


def _normalize_packages_method(method: str) -> str:
    m = (method or "").strip().lower()
    if m in {"invoice", "stars", "xtr"}:
        return "stars"
    if m == "sbp":
        return "sbp"
    return m


def _estimate_card_price(tokens: int, currency: str) -> str:
    if currency == "usd":
        cents = USD_PRICES_CENTS.get(tokens)
        if cents is None:
            cents = calculate_custom_price(tokens, "usd")["amount"]
        return format_usd_cents(cents)

    if currency == "eur":
        cents = EUR_PRICES_CENTS.get(tokens)
        if cents is None:
            cents = calculate_custom_price(tokens, "eur")["amount"]
        return format_eur_cents(cents)

    rubles = RUBLE_PRICES.get(tokens)
    if rubles is not None:
        return f"{format_rubles(rubles)} ₽"

    kopecks = calculate_custom_price(tokens, "rub")["amount"]
    return f"{kopecks / 100:.2f} ₽"


async def _packages_keyboard(lang: str, method: str) -> InlineKeyboardMarkup:
    m = _normalize_packages_method(method)
    rows: list[list[InlineKeyboardButton]] = []

    if m == "stars":
        for amount in sorted(ALLOWED_STAR_AMOUNTS):
            try:
                url = make_hub_link("stars", amount)
            except Exception:
                continue
            rows.append([InlineKeyboardButton(text=f"{amount} ✨", url=url)])

    elif m == "sbp":
        for tokens in sorted(ALLOWED_SBP_AMOUNTS):
            try:
                url = make_hub_link("sbp", tokens)
            except Exception:
                continue

            if lang.startswith("en"):
                usd_cents = USD_PRICES_CENTS.get(tokens)
                label = f"{tokens} Token" if usd_cents is None else f"{tokens} Token ~ {format_usd_cents(usd_cents)}"
            else:
                rub = RUBLE_PRICES.get(tokens)
                label = f"{tokens} Токен" if rub is None else f"{tokens} Токен ~ {format_rubles(rub)} руб"

            rows.append([InlineKeyboardButton(text=label, url=url)])

    if not rows:
        rows = [[InlineKeyboardButton(text=t(lang, "topup.package.unavailable"), callback_data="noop")]]

    rows.append([InlineKeyboardButton(text=t(lang, "common.back"), callback_data="topup_method:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("topup"))
async def topup(message: Message) -> None:
    db = _get_db()
    user_id = _message_user_id(message)
    user = await db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or _message_lang_hint(message))
    balance = await db.get_token_balance(user_id)
    await message.answer(_topup_main_text(lang, balance), reply_markup=method_keyboard(lang))


@router.message((F.text == t("ru", "kb.topup")) | (F.text == t("en", "kb.topup")))
async def topup_text(message: Message) -> None:
    await topup(message)


@router.callback_query(F.data == "topup_main")
async def topup_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    db = _get_db()
    cb_msg = _callback_message(callback)
    user_id = _callback_user_id(callback)
    await state.clear()
    user = await db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or _callback_lang_hint(callback))
    balance = await db.get_token_balance(user_id)
    text = _topup_main_text(lang, balance)
    await cb_msg.edit_text(text, reply_markup=method_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data.startswith("topup_method:"))
async def choose_method(callback: CallbackQuery, state: FSMContext) -> None:
    db = _get_db()
    cb_msg = _callback_message(callback)
    user_id = _callback_user_id(callback)
    user = await db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or _callback_lang_hint(callback))
    method = (callback.data or "").split(":", 1)[1].strip().lower()

    await state.clear()

    if method == "menu":
        balance = await db.get_token_balance(user_id)
        await cb_msg.edit_text(_topup_main_text(lang, balance), reply_markup=method_keyboard(lang))
        await callback.answer("OK")
        return

    if method == "card":
        await cb_msg.edit_text(t(lang, "topup.card_currency.title"), reply_markup=_card_currency_keyboard(lang))
        await callback.answer("OK")
        return

    kb = await _packages_keyboard(lang, method)
    await cb_msg.edit_text(
        f"{t(lang, 'topup.packages.title')}\n{t(lang, 'topup.link_hint')}",
        reply_markup=kb,
    )
    await callback.answer("OK")


@router.callback_query(F.data.startswith("topup_card_currency:"))
async def choose_card_currency(callback: CallbackQuery, state: FSMContext) -> None:
    db = _get_db()
    cb_msg = _callback_message(callback)
    user_id = _callback_user_id(callback)
    await callback.answer()
    user = await db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or _callback_lang_hint(callback))

    currency = (callback.data or "").split(":", 1)[1].strip().lower()
    if currency not in {"rub", "usd", "eur"}:
        await cb_msg.answer(t(lang, "topup.invalid_amount"))
        return

    method = f"card_{currency}"
    await state.update_data(card_method=method)

    await _safe_edit_text(
        callback,
        t(lang, "topup.card_currency.selected", currency=currency.upper()),
        reply_markup=_card_amount_keyboard(lang, method),
    )


@router.callback_query(F.data.startswith("topup_custom:"))
async def choose_custom_amount(callback: CallbackQuery, state: FSMContext) -> None:
    db = _get_db()
    cb_msg = _callback_message(callback)
    user_id = _callback_user_id(callback)
    user = await db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or _callback_lang_hint(callback))

    method = (callback.data or "").split(":", 1)[1].strip().lower()
    if method not in {"card_rub", "card_usd", "card_eur"}:
        await callback.answer(t(lang, "topup.invalid_amount"), show_alert=True)
        return

    await state.update_data(card_method=method)
    await state.set_state(CardTopupStates.waiting_amount)

    await cb_msg.edit_text(
        t(lang, "topup.card_custom_prompt", min=MIN_CUSTOM_TOKENS, max=MAX_CUSTOM_TOKENS)
    )
    await callback.answer("OK")


@router.message(CardTopupStates.waiting_amount)
async def card_custom_amount_received(message: Message, state: FSMContext) -> None:
    db = _get_db()
    user_id = _message_user_id(message)
    user = await db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or _message_lang_hint(message))

    try:
        tokens = int((message.text or "").strip())
    except Exception:
        await message.answer(t(lang, "topup.card_custom_invalid", min=MIN_CUSTOM_TOKENS, max=MAX_CUSTOM_TOKENS))
        return

    if not is_valid_custom_tokens(tokens):
        await message.answer(t(lang, "topup.card_custom_invalid", min=MIN_CUSTOM_TOKENS, max=MAX_CUSTOM_TOKENS))
        return

    data = await state.get_data()
    method = (data.get("card_method") or "card_rub").strip().lower()
    await state.clear()

    if method not in {"card_rub", "card_usd", "card_eur"}:
        method = "card_rub"

    currency = method.split("_", 1)[1]
    price_display = _estimate_card_price(tokens, currency)
    payment_url = make_hub_link(method, tokens)

    kb = _payment_link_keyboard(
        lang,
        payment_url,
        t(lang, "topup.card_pay_btn", price=price_display),
    )

    await message.answer(
        t(
            lang,
            "topup.card_link_ready",
            tokens=tokens,
            currency=currency.upper(),
            price=price_display,
        ),
        reply_markup=kb,
    )


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    try:
        await callback.answer("Оплата временно недоступна", show_alert=False)
    except Exception:
        pass


def topup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 ✨", callback_data="topup_invoice:1")],
            [
                InlineKeyboardButton(text="15 ✨", callback_data="topup_invoice:15"),
                InlineKeyboardButton(text="30 ✨", callback_data="topup_invoice:30"),
            ],
            [
                InlineKeyboardButton(text="50 ✨", callback_data="topup_invoice:50"),
                InlineKeyboardButton(text="100 ✨", callback_data="topup_invoice:100"),
            ],
        ]
    )


async def _send_invoice(message: Message, amount: int) -> None:
    db = _get_db()
    user_id = _message_user_id(message)
    user = await db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or _message_lang_hint(message))
    prices = [LabeledPrice(label=t(lang, "topup.invoice_label", amount=amount), amount=amount)]
    bot = message.bot
    if bot is None:
        raise RuntimeError("Bot instance is unavailable")
    await bot.send_invoice(
        chat_id=message.chat.id,
        title=t(lang, "topup.invoice_title"),
        description=t(lang, "topup.invoice_desc", amount=amount),
        payload=f"topup:{amount}",
        provider_token="",
        currency="XTR",
        prices=prices,
        start_parameter=f"topup_{amount}",
    )


@router.callback_query(F.data.startswith("topup_invoice:"))
async def choose_invoice_topup(callback: CallbackQuery) -> None:
    db = _get_db()
    cb_msg = _callback_message(callback)
    user_id = _callback_user_id(callback)
    data = callback.data or ""
    try:
        amount = int(data.split(":", 1)[1])
    except Exception:
        user = await db.get_user(user_id) or {}
        lang = normalize_lang(user.get("language_code") or _callback_lang_hint(callback))
        await callback.answer(t(lang, "topup.invalid_amount"), show_alert=True)
        return

    try:
        user = await db.get_user(user_id) or {}
        lang = normalize_lang(user.get("language_code") or _callback_lang_hint(callback))
        await cb_msg.answer(t(lang, "topup.prepare", amount=amount))
        await _send_invoice(cb_msg, amount)
        await callback.answer("OK")
    except Exception as e:
        _logger.exception("Failed to send Stars invoice: %s", e)
        user = await db.get_user(user_id) or {}
        lang = normalize_lang(user.get("language_code") or _callback_lang_hint(callback))
        await callback.answer(t(lang, "topup.invoice_fail"), show_alert=True)
        await cb_msg.answer(t(lang, "topup.payment_unavailable"))


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    db = _get_db()
    user_id = _message_user_id(message)
    sp = message.successful_payment
    if not sp or sp.currency != "XTR":
        user = await db.get_user(user_id) or {}
        lang = normalize_lang(user.get("language_code") or _message_lang_hint(message))
        await message.answer(t(lang, "topup.currency_mismatch"))
        return

    amount = int(sp.total_amount)
    current = await db.get_token_balance(user_id)
    new_balance = current + amount
    await db.set_token_balance(user_id, new_balance)

    user = await db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or _message_lang_hint(message))
    await message.answer(t(lang, "topup.success", amount=amount, balance=new_balance))
