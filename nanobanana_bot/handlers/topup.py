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
import logging


router = Router(name="topup")
_logger = logging.getLogger("nanobanana.topup")

_db: Database | None = None
_settings: Settings | None = None

def setup(database: Database, settings: Settings | None = None) -> None:
    global _db, _settings
    _db = database
    if settings is not None:
        _settings = settings


def method_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "topup.method.sbp"), callback_data="topup_method:sbp"),
                InlineKeyboardButton(text=t(lang, "topup.method.card"), callback_data="topup_method:card"),
                InlineKeyboardButton(text=t(lang, "topup.method.old_stars"), callback_data="topup_method:invoice"),
            ]
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
            f"{t(lang, 'topup.method.title')}"
        ),
        reply_markup=method_keyboard(lang),
    )


@router.message((F.text == t("ru", "kb.topup")) | (F.text == t("en", "kb.topup")))
async def topup_text(message: Message) -> None:
    await topup(message)


def _packages_keyboard(lang: str, method: str) -> InlineKeyboardMarkup:
    # Tribute split: SBP (web link) or Card (mini-app link)
    products = []
    if _settings and _settings.tribute_product_map:
        for tokens, pid in sorted(_settings.tribute_product_map.items()):
            if method == "card":
                slug = str(pid)
                # Mini-app expects startapp to be product slug; prefix 'p' only if missing
                if not slug.startswith("p"):
                    slug = "p" + slug
                url = f"https://t.me/tribute/app?startapp={slug}"
            else:
                # Web link uses /p/<slug> directly
                url = f"https://web.tribute.tg/p/{pid}"
            products.append([InlineKeyboardButton(text=f"{tokens} ✨", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=products or [[InlineKeyboardButton(text=t(lang, "topup.package.unavailable"), callback_data="noop")]])


@router.callback_query(F.data.startswith("topup_method:"))
async def choose_method(callback: CallbackQuery) -> None:
    assert _db is not None
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    method = (callback.data or "").split(":", 1)[1]
    if method == "invoice":
        # Show amounts for Stars invoice (old method)
        await callback.message.answer(t(lang, "topup.choose"), reply_markup=topup_keyboard())
        await callback.answer("OK")
        return
    # Tribute: show packages with links (sbp or card)
    kb = _packages_keyboard(lang, method)
    await callback.message.answer(
        f"{t(lang, 'topup.packages.title')}\n{t(lang, 'topup.link_hint')}",
        reply_markup=kb,
    )
    await callback.answer("OK")


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
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    prices = [LabeledPrice(label=t(lang, "topup.invoice_label", amount=amount), amount=amount)]
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title=t(lang, "topup.invoice_title"),
        description=t(lang, "topup.invoice_desc", amount=amount),
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
    current = await _db.get_token_balance(message.from_user.id)
    new_balance = current + amount
    await _db.set_token_balance(message.from_user.id, new_balance)

    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    await message.answer(t(lang, "topup.success", amount=amount, balance=new_balance))