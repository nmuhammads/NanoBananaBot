from aiogram import Router, html
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ..database import Database
from ..cache import Cache


router = Router(name="start")

_db: Database | None = None
_cache: Cache | None = None


def setup(database: Database, cache: Cache) -> None:
    global _db, _cache
    _db = database
    _cache = cache


@router.message(CommandStart())
async def start(message: Message) -> None:
    assert _db is not None and _cache is not None
    user = await _db.get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        language_code=message.from_user.language_code,
    )
    balance = await _cache.get_balance(message.from_user.id)
    if balance == 0:
        # If no cache, fetch from DB and mirror into cache
        db_balance = await _db.get_token_balance(message.from_user.id)
        if db_balance:
            await _cache.set_balance(message.from_user.id, db_balance)
            balance = db_balance

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
        )
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