from aiogram import Router, html, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext

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
async def start(message: Message, state: FSMContext) -> None:
    assert _db is not None
    # Всегда сбрасываем состояние при /start, чтобы начать процесс заново
    await state.clear()
    # Идентификаторы пользователя и источника (имя бота) для регистрации подписки
    user_id = int(message.from_user.id)
    bot_me = await message.bot.get_me()
    bot_name = bot_me.username if hasattr(bot_me, "username") else None
    txt = message.text or ""
    is_ref_link = False
    raw_ref = None
    try:
        if txt.startswith("/start"):
            parts = txt.split(maxsplit=1)
            if len(parts) > 1:
                val = parts[1].strip()
                if val.lower().startswith("ref_"):
                    is_ref_link = True
                    raw_ref = val[4:]
    except Exception:
        is_ref_link = False
    # Если пользователя нет в базе — это первый запуск: сначала попросим выбрать язык
    existing = await _db.get_user(user_id)
    if not existing:
        ref_safe = None
        if is_ref_link:
            try:
                tag = (raw_ref or "").lstrip("@").strip()
                safe = "".join(ch for ch in tag if ch.isalnum() or ch in {"_", "-"})
                ref_safe = safe if safe else None
            except Exception:
                ref_safe = None
        payload = {
            "user_id": user_id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "language_code": message.from_user.language_code,
        }
        if ref_safe is not None:
            payload["ref"] = ref_safe
        _db.client.table("users").upsert(payload, on_conflict="user_id").execute()
        # Регистрация подписки на текущего бота (id + username бота)
        if bot_name:
            _db.client.table("bot_subscriptions").upsert({
                "user_id": user_id,
                "bot_source": bot_name,
            }, on_conflict="user_id,bot_source").execute()
        lang_hint = normalize_lang(message.from_user.language_code)
        await message.answer(
            t(lang_hint, "start.choose_language"),
            reply_markup=_language_keyboard(),
        )
        return

    # Для повторного /start добавим/актуализируем подписку (без изменений UI)
    if bot_name:
        _db.client.table("bot_subscriptions").upsert({
            "user_id": user_id,
            "bot_source": bot_name,
        }, on_conflict="user_id,bot_source").execute()

    if is_ref_link and not existing.get("ref"):
        ref_safe = None
        try:
            tag = (raw_ref or "").lstrip("@").strip()
            safe = "".join(ch for ch in tag if ch.isalnum() or ch in {"_", "-"})
            ref_safe = safe if safe else None
        except Exception:
            ref_safe = None
        if ref_safe is not None:
            try:
                await _db.set_ref(user_id, ref_safe)
            except Exception:
                pass

    # Иначе — обычное приветствие с уже выбранным языком
    lang = normalize_lang(existing.get("language_code") or message.from_user.language_code)
    balance = await _db.get_token_balance(user_id)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(lang, "kb.profile")),
                KeyboardButton(text=t(lang, "kb.topup")),
            ],
            [
                KeyboardButton(text=t(lang, "kb.generate")),
                KeyboardButton(text=t(lang, "kb.avatars")),
            ],
            [
                KeyboardButton(text=t(lang, "kb.seedream_4_5")),
            ],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        t(lang, "start.welcome", name=html.bold(message.from_user.full_name), balance=balance),
        reply_markup=keyboard,
    )


# Запуск главного меню по текстовой кнопке
@router.message((F.text == t("ru", "kb.start")) | (F.text == t("en", "kb.start")))
async def start_text(message: Message, state: FSMContext) -> None:
    # Сбрасываем состояние и показываем главное меню
    await start(message, state)


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
            [
                KeyboardButton(text=t(lang, "kb.generate")),
                KeyboardButton(text=t(lang, "kb.avatars")),
            ],
            [
                KeyboardButton(text=t(lang, "kb.seedream_4_5")),
            ],
        ],
        resize_keyboard=True,
    )
    await callback.message.answer(
        t(lang, "start.welcome", name=html.bold(callback.from_user.full_name), balance=balance),
        reply_markup=keyboard,
    )
