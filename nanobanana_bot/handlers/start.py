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
            [KeyboardButton(text="Профиль 👤"), KeyboardButton(text="Сгенерировать 🖼️")],
            [KeyboardButton(text="Пополнить баланс ✨")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        (
            f"Привет, {html.bold(message.from_user.full_name)}!\n\n"
            f"Добро пожаловать в NanoBanana Bot — генерируем изображения по вашему тексту.\n\n"
            f"Ваш баланс токенов: <b>{balance}</b>\n\n"
            f"Что дальше:\n"
            f"• Сгенерировать изображение: отправьте /generate и ваш запрос.\n"
            f"  Пример: /generate космический нано банан на фоне галактики\n"
            f"• Профиль: /profile — ваши данные и баланс\n"
            f"• Список команд: /help"
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