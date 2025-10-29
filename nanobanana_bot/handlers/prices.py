from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from ..database import Database
from ..utils.i18n import t, normalize_lang
from ..utils.prices import RUBLE_PRICES, USD_PRICES, format_rubles, format_usd


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

    # Build prices list per locale
    lines: list[str] = []
    header_key = "prices.rubles.header"
    if lang == "en":
        for tokens, usd in sorted(USD_PRICES.items()):
            lines.append(f"{tokens} tokens — ${format_usd(usd)}")
        header_key = "prices.usd.header"
    else:
        for tokens, rub in sorted(RUBLE_PRICES.items()):
            lines.append(f"{tokens} токенов — {format_rubles(rub)} руб")
    prices_block = "\n".join(lines)

    text = (
        f"{t(lang, 'prices.title')}\n\n"
        f"{t(lang, header_key)}\n"
        f"{prices_block}\n\n"
        f"{t(lang, 'prices.stars.header')}\n"
        f"{t(lang, 'prices.stars.line')}\n\n"
        f"{t(lang, 'prices.disclaimer')}"
    )

    await message.answer(text)


# Fallback text triggers
@router.message(F.text.regexp(r"(?i)^\s*\/prices\s*$"))
async def prices_text(message: Message) -> None:
    await prices(message)