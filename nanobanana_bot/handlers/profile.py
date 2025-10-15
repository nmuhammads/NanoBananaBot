from aiogram import Router, html, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from ..database import Database


router = Router(name="profile")

_db: Database | None = None


def setup(database: Database) -> None:
    global _db
    _db = database


@router.message(Command("profile"))
async def profile(message: Message) -> None:
    assert _db is not None

    user = await _db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        language_code=message.from_user.language_code,
    )

    # Баланс хранится только в Supabase
    balance = await _db.get_token_balance(message.from_user.id)

    username = user.get("username")
    first_name = user.get("first_name")
    last_name = user.get("last_name")
    language_code = user.get("language_code")

    full_name = (first_name or "") + (" " + last_name if last_name else "")
    full_name = full_name.strip() or message.from_user.full_name

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Профиль 👤"), KeyboardButton(text="Пополнить баланс ✨")],
            [KeyboardButton(text="Сгенерировать 🖼️")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        (
            f"Профиль пользователя\n\n"
            f"Имя: {html.bold(full_name)}\n"
            f"Username: {('@' + username) if username else '—'}\n"
            f"ID: {message.from_user.id}\n"
            f"Язык: {language_code or '—'}\n\n"
            f"Баланс токенов: <b>{balance}</b>\n"
            f"Команды: /help"
        ),
        reply_markup=keyboard,
    )


@router.message(F.text == "Профиль 👤")
async def profile_text(message: Message) -> None:
    await profile(message)