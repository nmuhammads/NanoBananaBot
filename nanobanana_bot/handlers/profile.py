from aiogram import Router, html
from aiogram.filters import Command
from aiogram.types import Message

from ..database import Database
from ..cache import Cache


router = Router(name="profile")

_db: Database | None = None
_cache: Cache | None = None


def setup(database: Database, cache: Cache) -> None:
    global _db, _cache
    _db = database
    _cache = cache


@router.message(Command("profile"))
async def profile(message: Message) -> None:
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
        db_balance = await _db.get_token_balance(message.from_user.id)
        if db_balance:
            await _cache.set_balance(message.from_user.id, db_balance)
            balance = db_balance

    username = user.get("username")
    first_name = user.get("first_name")
    last_name = user.get("last_name")
    language_code = user.get("language_code")

    full_name = (first_name or "") + (" " + last_name if last_name else "")
    full_name = full_name.strip() or message.from_user.full_name

    await message.answer(
        (
            f"Профиль пользователя\n\n"
            f"Имя: {html.bold(full_name)}\n"
            f"Username: {('@' + username) if username else '—'}\n"
            f"ID: {message.from_user.id}\n"
            f"Язык: {language_code or '—'}\n\n"
            f"Баланс токенов: <b>{balance}</b>\n"
            f"Команды: /help"
        )
    )