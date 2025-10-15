from aiogram import Router, html
from aiogram.filters import CommandStart
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
            f"Это NanoBanana Bot — генерация изображений по тексту.\n\n"
            f"Ваш баланс токенов: <b>{balance}</b>\n"
            f"Команды: /help, /generate <описание>"
        )
    )


@router.message()
async def fallback(message: Message) -> None:
    # Simple echo for non-command messages in start router
    if message.text and message.text.strip().lower() in {"help", "/help"}:
        await help(message)


async def help(message: Message) -> None:
    await message.answer(
        (
            "Как использовать:\n"
            "- /generate <prompt> — создаёт изображение по описанию.\n"
            "- Пример: /generate космический нано банан на фоне галактики.\n"
        )
    )