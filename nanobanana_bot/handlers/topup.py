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
import logging


router = Router(name="topup")
_logger = logging.getLogger("nanobanana.topup")

_db: Database | None = None


def setup(database: Database) -> None:
    global _db
    _db = database


def topup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 ✨", callback_data="topup:1")],
            [
                InlineKeyboardButton(text="15 ✨", callback_data="topup:15"),
                InlineKeyboardButton(text="30 ✨", callback_data="topup:30"),
            ],
            [
                InlineKeyboardButton(text="50 ✨", callback_data="topup:50"),
                InlineKeyboardButton(text="100 ✨", callback_data="topup:100"),
            ],
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
            f"{t(lang, 'topup.choose')}"
        ),
        reply_markup=topup_keyboard(),
    )


@router.message((F.text == t("ru", "kb.topup")) | (F.text == t("en", "kb.topup")))
async def topup_text(message: Message) -> None:
    await topup(message)


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


@router.callback_query(F.data.startswith("topup:"))
async def choose_topup(callback: CallbackQuery) -> None:
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