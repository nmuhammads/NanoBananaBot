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


router = Router(name="topup")

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
    await message.answer(
        "Выберите сумму пополнения токенов (1 ✨ = 1 токен):",
        reply_markup=topup_keyboard(),
    )


@router.message(F.text == "Пополнить баланс")
async def topup_text(message: Message) -> None:
    await topup(message)


async def _send_invoice(message: Message, amount: int) -> None:
    prices = [LabeledPrice(label=f"Пополнение {amount} токенов", amount=amount)]
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title="Пополнение токенов",
        description=f"Покупка {amount} токенов (Telegram Stars)",
        payload=f"topup:{amount}",
        provider_token="",  # Stars для цифровых товаров — без провайдера
        currency="XTR",
        prices=prices,
    )


@router.callback_query(F.data.startswith("topup:"))
async def choose_topup(callback: CallbackQuery) -> None:
    data = callback.data or ""
    try:
        amount = int(data.split(":", 1)[1])
    except Exception:
        await callback.answer("Некорректная сумма", show_alert=True)
        return

    await _send_invoice(callback.message, amount)
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    # Разрешаем оплату без дополнительных проверок
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    assert _db is not None
    sp = message.successful_payment
    if not sp or sp.currency != "XTR":
        await message.answer("Оплата не в валюте XTR, обращайтесь в поддержку.")
        return

    amount = int(sp.total_amount)
    current = await _db.get_token_balance(message.from_user.id)
    new_balance = current + amount
    await _db.set_token_balance(message.from_user.id, new_balance)

    await message.answer(
        f"Успешная оплата: начислено {amount} токенов. Ваш новый баланс: {new_balance}.\nСпасибо!"
    )