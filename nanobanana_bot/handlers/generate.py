from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..utils.nanobanana import NanoBananaClient
from ..database import Database
from ..cache import Cache


router = Router(name="generate")

_client: NanoBananaClient | None = None
_db: Database | None = None
_cache: Cache | None = None


def setup(client: NanoBananaClient, database: Database, cache: Cache) -> None:
    global _client, _db, _cache
    _client = client
    _db = database
    _cache = cache


@router.message(Command("generate"))
async def generate(message: Message) -> None:
    assert _client is not None and _db is not None and _cache is not None

    text = message.text or ""
    parts = text.split(maxsplit=1)
    prompt = parts[1].strip() if len(parts) > 1 else ""
    if not prompt:
        await message.answer(
            "Добавьте текст после команды: /generate космический нано банан на фоне галактики"
        )
        return

    # Token check (assumption: 1 token per generation)
    balance = await _cache.get_balance(message.from_user.id)
    if balance <= 0:
        await message.answer("Недостаточно токенов. Пополните баланс или обратитесь в поддержку.")
        return

    # Track generation in Supabase
    generation = await _db.create_generation(message.from_user.id, prompt)
    gen_id = generation.get("id")

    try:
        image_url = await _client.generate_image(prompt)
    except Exception as e:
        # Mark generation failed
        if gen_id is not None:
            await _db.mark_generation_failed(gen_id, str(e))
        await message.answer(f"Ошибка генерации: {e}")
        return

    # Decrement token and persist
    new_balance = await _cache.increment_balance(message.from_user.id, -1)
    await _db.set_token_balance(message.from_user.id, new_balance)

    # Mark generation completed
    if gen_id is not None:
        await _db.mark_generation_completed(gen_id, image_url)

    await message.answer_photo(photo=image_url, caption=f"Готово! Остаток токенов: {new_balance}")