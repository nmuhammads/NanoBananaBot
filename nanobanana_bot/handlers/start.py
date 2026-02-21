from aiogram import Router, html, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
import re

from ..database import Database
from ..utils.i18n import t, normalize_lang


router = Router(name="start")

_db: Database | None = None


def setup(database: Database) -> None:
    global _db
    _db = database


GENERATION_METADATA_PATTERN = re.compile(r'\s*\[type=[^\]]+\]\s*$')

def clean_prompt_text(text: str) -> str:
    """Remove generation metadata suffix from prompt text."""
    if not text:
        return ""
    return GENERATION_METADATA_PATTERN.sub('', text).rstrip()


def _language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang:ru"),
                InlineKeyboardButton(text="English 🇺🇸", callback_data="lang:en"),
            ]
        ]
    )

def get_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "kb.generate")), KeyboardButton(text=t(lang, "kb.nanobanana_pro"))],
            [KeyboardButton(text=t(lang, "kb.profile")), KeyboardButton(text=t(lang, "avatars.btn_label")), KeyboardButton(text=t(lang, "kb.topup"))],
        ],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    assert _db is not None
    ref_value = None
    gen_id = None
    try:
        txt = message.text or ""
        if txt.startswith("/start"):
            parts = txt.split(maxsplit=1)
            if len(parts) > 1:
                ref_value = parts[1].strip()
    except Exception:
        ref_value = None
    try:
        bot_me = await message.bot.get_me()
        bot_name = getattr(bot_me, "username", None)
        if bot_name:
            await _db.ensure_bot_subscription(int(message.from_user.id), bot_name)
    except Exception:
        pass
    try:
        if ref_value:
            val = ref_value.strip()
            if val.lower().startswith("ref_"):
                # Парсинг опционального суффикса _gen_{id}
                ref_part = val
                if "_gen_" in val:
                    parts = val.split("_gen_")
                    if len(parts) == 2:
                        ref_part = parts[0]
                        try:
                            gen_id = int(parts[1])
                        except ValueError:
                            gen_id = str(parts[1])

                tag = ref_part[4:].lstrip("@").strip()
                safe = "".join(ch for ch in tag if ch.isalnum() or ch in {"_", "-"})
                if safe:
                    user = await _db.get_user(message.from_user.id)
                    if not user:
                        await _db.upsert_user_ref(message.from_user.id, safe)
                    elif not user.get("ref"):
                        await _db.set_ref(message.from_user.id, safe)
    except Exception:
        pass
    # Если пользователя нет в базе — это первый запуск: автоматическая регистрация с языком пользователя (fallback to en)
    existing = await _db.get_user(message.from_user.id)
    if not existing:
        lang_code = message.from_user.language_code or "en"
        lang_code = "ru" if lang_code.lower().startswith("ru") else "en"
        
        await _db.get_or_create_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=lang_code,
        )
        existing = await _db.get_user(message.from_user.id) or {}

    # Иначе — обычное приветствие с уже выбранным языком
    lang = normalize_lang(existing.get("language_code") or message.from_user.language_code)
    balance = await _db.get_token_balance(message.from_user.id)

    # Если передан gen_id, переходим к FSM генерации
    if gen_id is not None:
        is_author_prompt = isinstance(gen_id, str) and str(gen_id).lower().startswith("p")
        generation_data = None
        if is_author_prompt:
            try:
                num_id = int(str(gen_id)[1:])
                author_prompt = await _db.get_author_prompt(num_id)
                if author_prompt and author_prompt.get("prompt_text"):
                    generation_data = {"prompt": author_prompt["prompt_text"]}
            except ValueError:
                pass
        else:
            generation_data = await _db.get_generation(gen_id)

        if generation_data and generation_data.get("prompt"):
            prompt_text = clean_prompt_text(generation_data["prompt"])
            update_kwargs = {
                "gen_type": "text_photo",
                "prompt": prompt_text,
                "lang": lang,
                "preferred_model": "nano-banana-pro",
                "ratio": "3:4",
                "resolution": "2K",
                "tokens_required": 10
            }
            
            await state.update_data(**update_kwargs)
            
            avatars = await _db.list_avatars(message.from_user.id)
            if avatars:
                await state.set_state("GenerateStates:choosing_avatar")
                from .generate import avatar_source_keyboard
                await message.answer(
                    f"✨ 🍌 NanoBanana Pro\n\nПромпт получен. " + t(lang, "avatars.choose_source"),
                    reply_markup=avatar_source_keyboard(lang)
                )
            else:
                await state.update_data(photos_needed=1, photos=[])
                await state.set_state("GenerateStates:waiting_photos")
                await message.answer(
                    f"✨ 🍌 NanoBanana Pro\n\nПромпт получен. " + t(lang, "gen.upload_photo")
                )
            return

    keyboard = get_main_keyboard(lang)


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
    keyboard = get_main_keyboard(lang)

    await callback.message.answer(
        t(lang, "start.welcome", name=html.bold(html.quote(str(callback.from_user.full_name or ''))), balance=balance),
        reply_markup=keyboard,
    )

# Обработка текстовой кнопки "Старт ⏮️" из ReplyKeyboard
@router.message(F.text.casefold().in_({"старт ⏮️", "start ⏮️"}))
async def start_button(message: Message) -> None:
    # Переиспользуем основной хэндлер /start
    await start(message)
