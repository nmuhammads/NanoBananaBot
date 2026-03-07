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
_logger = logging.getLogger("seedream.topup")

_db: Database | None = None
_settings: Settings | None = None


class CardTopupStates(StatesGroup):
    waiting_amount = State()


def setup(database: Database, settings: Settings | None = None) -> None:
    global _db, _settings
    _db = database
    _settings = settings


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
            [InlineKeyboardButton(text=t(lang, "kb.start"), callback_data="topup_method:menu")],
        ]
    )


def _card_amount_keyboard(lang: str, method: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "topup.custom_input"), callback_data=f"topup_custom:{method}")],
            [InlineKeyboardButton(text=t(lang, "topup.back_to_currency"), callback_data="topup_method:card")],
            [InlineKeyboardButton(text=t(lang, "kb.start"), callback_data="topup_method:menu")],
        ]
    )


def _payment_link_keyboard(lang: str, url: str, button_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=url)],
            [InlineKeyboardButton(text=t(lang, "kb.start"), callback_data="topup_method:menu")],
        ]
    )


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

    rows.append([InlineKeyboardButton(text=t(lang, "kb.start"), callback_data="topup_method:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("topup"))
async def topup(message: Message) -> None:
    assert _db is not None
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    balance = await _db.get_token_balance(message.from_user.id)
    await message.answer(_topup_main_text(lang, balance), reply_markup=method_keyboard(lang))


@router.message((F.text == t("ru", "kb.topup")) | (F.text == t("en", "kb.topup")))
async def topup_text(message: Message) -> None:
    await topup(message)


@router.callback_query(F.data.startswith("topup_method:"))
async def choose_method(callback: CallbackQuery, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    method = (callback.data or "").split(":", 1)[1].strip().lower()
    await state.clear()

    if method == "menu":
        balance = await _db.get_token_balance(callback.from_user.id)
        await callback.message.answer(_topup_main_text(lang, balance), reply_markup=method_keyboard(lang))
        await callback.answer("OK")
        return

    if method == "card":
        await callback.message.answer(t(lang, "topup.card_currency.title"), reply_markup=_card_currency_keyboard(lang))
        await callback.answer("OK")
        return

    kb = await _packages_keyboard(lang, method)
    await callback.message.answer(
        f"{t(lang, 'topup.packages.title')}\n{t(lang, 'topup.link_hint')}",
        reply_markup=kb,
    )
    await callback.answer("OK")


@router.callback_query(F.data.startswith("topup_card_currency:"))
async def choose_card_currency(callback: CallbackQuery, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)

    currency = (callback.data or "").split(":", 1)[1].strip().lower()
    if currency not in {"rub", "usd", "eur"}:
        await callback.answer(t(lang, "topup.invalid_amount"), show_alert=True)
        return

    method = f"card_{currency}"
    await state.update_data(card_method=method)

    await callback.message.answer(
        t(lang, "topup.card_currency.selected", currency=currency.upper()),
        reply_markup=_card_amount_keyboard(lang, method),
    )
    await callback.answer("OK")


@router.callback_query(F.data.startswith("topup_custom:"))
async def choose_custom_amount(callback: CallbackQuery, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)

    method = (callback.data or "").split(":", 1)[1].strip().lower()
    if method not in {"card_rub", "card_usd", "card_eur"}:
        await callback.answer(t(lang, "topup.invalid_amount"), show_alert=True)
        return

    await state.update_data(card_method=method)
    await state.set_state(CardTopupStates.waiting_amount)

    await callback.message.answer(
        t(lang, "topup.card_custom_prompt", min=MIN_CUSTOM_TOKENS, max=MAX_CUSTOM_TOKENS)
    )
    await callback.answer("OK")


@router.message(CardTopupStates.waiting_amount)
async def card_custom_amount_received(message: Message, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)

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
    credited_tokens = amount // 2
    prices = [LabeledPrice(label=t(lang, "topup.invoice_label", amount=credited_tokens), amount=amount)]
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title=t(lang, "topup.invoice_title"),
        description=t(lang, "topup.invoice_desc", amount=credited_tokens),
        payload=f"topup:{amount}",
        provider_token="",
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
    credited_tokens = amount // 2
    current = await _db.get_token_balance(message.from_user.id)
    new_balance = current + credited_tokens
    await _db.set_token_balance(message.from_user.id, new_balance)

    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    await message.answer(t(lang, "topup.success", amount=credited_tokens, balance=new_balance))
