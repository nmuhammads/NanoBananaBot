from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from ..database import Database
from ..utils.i18n import t, normalize_lang
from ..utils.prices import RUBLE_PRICES, format_rubles


router = Router(name="prices")

_db: Database | None = None


def setup(database: Database) -> None:
    global _db
    _db = database


@router.message(Command("prices"))
async def prices(message: Message) -> None:
    assert _db is not None
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)

    # Build ruble prices list from shared mapping
    lines: list[str] = []
    for tokens, rub in sorted(RUBLE_PRICES.items()):
        lines.append(f"{tokens} токенов — {format_rubles(rub)} руб")
    rubles_block = "\n".join(lines)

    text = (
        f"{t(lang, 'prices.title')}\n\n"
        f"{t(lang, 'prices.rubles.header')}\n"
        f"{rubles_block}\n\n"
        f"{t(lang, 'prices.stars.header')}\n"
        f"{t(lang, 'prices.stars.line')}\n\n"
        f"{t(lang, 'prices.disclaimer')}"
    )

    await message.answer(text)


# Fallback text triggers
@router.message(F.text.regexp(r"(?i)^\s*\/prices\s*$"))
async def prices_text(message: Message) -> None:
    await prices(message)