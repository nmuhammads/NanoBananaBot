from aiogram import Router, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from ..database import Database


router = Router(name="start")

_db: Database | None = None


def setup(database: Database) -> None:
    global _db
    _db = database


@router.message(CommandStart())
async def start(message: Message) -> None:
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

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Профиль 👤"), KeyboardButton(text="Пополнить баланс ✨")],
            [KeyboardButton(text="Сгенерировать 🖼️")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        (
            f"🍌 <b>NanoBanana Bot</b>\n\n"
            f"Привет, {html.bold(message.from_user.full_name)}! Добро пожаловать 👋\n\n"
            f"✨ Возможности:\n"
            f"• Генерация изображений по тексту\n"
            f"• Текст + фото, несколько фото\n\n"
            f"💳 Стоимость: <b>4 токена</b> за изображение\n"
            f"💰 Ваш баланс: <b>{balance}</b> ✨\n\n"
            f"Выберите действие на клавиатуре:"
        ),
        reply_markup=keyboard,
    )


# Убираем универсальный обработчик без фильтров, чтобы не мешать командам


@router.message(Command("help"))
async def help(message: Message) -> None:
    await message.answer(
        (
            "Список команд:\n"
            "- /start — приветствие и синхронизация баланса\n"
            "- /profile — информация о пользователе и баланс\n"
            "- /generate — создать изображение по текстовому запросу\n\n"
            "Пример генерации:\n"
            "/generate космический нано банан на фоне галактики"
        )
    )