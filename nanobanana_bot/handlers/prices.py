from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from ..database import Database
from ..utils.i18n import t, normalize_lang
from ..utils.prices import (
    RUBLE_PRICES,
    USD_PRICES_CENTS,
    EUR_PRICES_CENTS,
    format_rubles,
    format_usd_cents,
    format_eur_cents,
)


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

    usd_block = "\n".join(
        f"{tokens} {'tokens' if lang == 'en' else 'токенов'} — {format_usd_cents(usd)}"
        for tokens, usd in sorted(USD_PRICES_CENTS.items())
    )
    eur_block = "\n".join(
        f"{tokens} {'tokens' if lang == 'en' else 'токенов'} — {format_eur_cents(eur)}"
        for tokens, eur in sorted(EUR_PRICES_CENTS.items())
    )

    if lang == "en":
        text = (
            f"{t(lang, 'prices.title')}\n\n"
            f"{t(lang, 'prices.usd.header')}\n"
            f"{usd_block}\n\n"
            f"{t(lang, 'prices.eur.header')}\n"
            f"{eur_block}\n\n"
            f"{t(lang, 'prices.stars.header')}\n"
            f"{t(lang, 'prices.stars.line')}\n\n"
            f"{t(lang, 'prices.disclaimer')}"
        )
    else:
        rub_block = "\n".join(
            f"{tokens} токенов — {format_rubles(rub)} руб"
            for tokens, rub in sorted(RUBLE_PRICES.items())
        )
        text = (
            f"{t(lang, 'prices.title')}\n\n"
            f"{t(lang, 'prices.rubles.header')}\n"
            f"{rub_block}\n\n"
            f"{t(lang, 'prices.usd.header')}\n"
            f"{usd_block}\n\n"
            f"{t(lang, 'prices.eur.header')}\n"
            f"{eur_block}\n\n"
            f"{t(lang, 'prices.stars.header')}\n"
            f"{t(lang, 'prices.stars.line')}\n\n"
            f"{t(lang, 'prices.disclaimer')}"
        )

    await message.answer(text)


# Fallback text triggers
@router.message(F.text.regexp(r"(?i)^\s*\/prices\s*$"))
async def prices_text(message: Message) -> None:
    await prices(message)
