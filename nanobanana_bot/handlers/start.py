from aiogram import Router, html, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from ..database import Database
from ..utils.i18n import t, normalize_lang


router = Router(name="start")

_db: Database | None = None


def setup(database: Database) -> None:
    global _db
    _db = database


def _language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang:ru"),
                InlineKeyboardButton(text="English 🇺🇸", callback_data="lang:en"),
            ]
        ]
    )


@router.message(CommandStart())
async def start(message: Message) -> None:
    assert _db is not None
    try:
        bot_me = await message.bot.get_me()
        bot_name = getattr(bot_me, "username", None)
        if bot_name:
            await _db.ensure_bot_subscription(int(message.from_user.id), bot_name)
    except Exception:
        pass
    # Если пользователя нет в базе — это первый запуск: сначала попросим выбрать язык
    existing = await _db.get_user(message.from_user.id)
    if not existing:
        lang_hint = normalize_lang(message.from_user.language_code)
        await message.answer(
            t(lang_hint, "start.choose_language"),
            reply_markup=_language_keyboard(),
        )
        return

    # Иначе — обычное приветствие с уже выбранным языком
    lang = normalize_lang(existing.get("language_code") or message.from_user.language_code)
    balance = await _db.get_token_balance(message.from_user.id)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(lang, "kb.profile")),
                KeyboardButton(text=t(lang, "kb.topup")),
            ],
            [KeyboardButton(text=t(lang, "kb.generate")), KeyboardButton(text=t(lang, "kb.nanobanana_pro"))],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        t(lang, "start.welcome", name=html.bold(html.quote(str(message.from_user.full_name or ''))), balance=balance),
        reply_markup=keyboard,
    )


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    assert _db is not None
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    await message.answer(t(lang, "help.body"))


@router.message(Command("lang"))
async def lang_cmd(message: Message) -> None:
    assert _db is not None
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    await message.answer(t(lang, "start.choose_language"), reply_markup=_language_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(callback: CallbackQuery) -> None:
    assert _db is not None
    lang_code = callback.data.split(":", 1)[1]
    # Если пользователя ещё нет — создадим с выбранным языком
    user = await _db.get_user(callback.from_user.id)
    if not user:
        await _db.get_or_create_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            language_code=lang_code,
        )
    else:
        await _db.set_language_code(callback.from_user.id, lang_code)
    # Обновляем локаль для ответа
    lang = normalize_lang(lang_code)
    await callback.message.edit_text(t(lang, "lang.updated", lang_flag=("🇷🇺" if lang == "ru" else "🇺🇸")))

    # Показ приветствия и клавиатуры на выбранном языке
    balance = await _db.get_token_balance(callback.from_user.id)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(lang, "kb.profile")),
                KeyboardButton(text=t(lang, "kb.topup")),
            ],
            [KeyboardButton(text=t(lang, "kb.generate")), KeyboardButton(text=t(lang, "kb.nanobanana_pro"))],
        ],
        resize_keyboard=True,
    )
    await callback.message.answer(
        t(lang, "start.welcome", name=html.bold(html.quote(str(callback.from_user.full_name or ''))), balance=balance),
        reply_markup=keyboard,
    )

# Обработка текстовой кнопки "Старт ⏮️" из ReplyKeyboard
@router.message(F.text.casefold().in_({"старт ⏮️", "start ⏮️"}))
async def start_button(message: Message) -> None:
    # Переиспользуем основной хэндлер /start
    await start(message)
