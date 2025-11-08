from aiogram import Router, html, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from ..database import Database
from ..utils.i18n import t, normalize_lang


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

    balance = await _db.get_token_balance(message.from_user.id)

    username = user.get("username")
    first_name = user.get("first_name")
    last_name = user.get("last_name")
    language_code = user.get("language_code")

    full_name = (first_name or "") + (" " + last_name if last_name else "")
    full_name = full_name.strip() or message.from_user.full_name

    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "kb.profile")), KeyboardButton(text=t(lang, "kb.topup"))],
            [KeyboardButton(text=t(lang, "kb.generate"))],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        (
            f"{t(lang, 'profile.title')}\n\n"
            f"{t(lang, 'profile.name', name=html.bold(html.quote(str(full_name or ''))))}\n"
            f"{t(lang, 'profile.username', username=('@' + username) if username else '—')}\n"
            f"{t(lang, 'profile.id', id=message.from_user.id)}\n"
            f"{t(lang, 'profile.lang', lang_code=language_code or '—')}\n\n"
            f"{t(lang, 'profile.balance', balance=balance)}\n\n"
            f"{t(lang, 'profile.actions')}"
        ),
        reply_markup=keyboard,
    )


@router.message((F.text == t("ru", "kb.profile")) | (F.text == t("en", "kb.profile")))
async def profile_text(message: Message) -> None:
    await profile(message)

# Дополнительный fallback, если текст кнопки отличается или содержит лишние символы/эмодзи
@router.message(F.text.regexp(r"(?i)^\s*\/?\s*(Профиль|Profile).*$"))
async def profile_text_fallback(message: Message) -> None:
    await profile(message)