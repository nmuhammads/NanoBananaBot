from aiogram import Router, F, html
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BufferedInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    URLInputFile,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from ..utils.nanobanana import NanoBananaClient
from ..database import Database
from ..utils.i18n import t, normalize_lang
from ..utils.r2 import R2Client
from ..cache import Cache
import asyncio
import logging
import httpx


router = Router(name="generate")

_client: NanoBananaClient | None = None
_db: Database | None = None
_cache: Cache | None = None
_r2: R2Client | None = None
_logger = logging.getLogger("nanobanana.generate")

def setup(client: NanoBananaClient, database: Database, cache: Cache | None = None, r2_client: R2Client | None = None) -> None:
    global _client, _db, _cache, _r2
    _client = client
    _db = database
    _cache = cache
    _r2 = r2_client

class GenerateStates(StatesGroup):
    choosing_type = State()
    choosing_avatar = State()
    waiting_prompt = State()
    waiting_photo_count = State()
    waiting_photos = State()
    choosing_ratio = State()
    choosing_resolution = State()
    confirming = State()
    repeating_confirm = State()


def truncate_prompt(prompt: str, max_length: int = 500) -> str:
    """Truncate prompt for display in summary to avoid MESSAGE_TOO_LONG error."""
    if len(prompt) <= max_length:
        return prompt
    return prompt[:max_length] + "..."


# Maximum prompt length to avoid MESSAGE_TOO_LONG error in Telegram
# API supports up to 10000, but Telegram message limit is ~4096
MAX_PROMPT_LENGTH = 4000



GEN_TRIGGERS = {
    t("ru", "kb.generate"),
    t("en", "kb.generate"),
    t("ru", "kb.new_generation"),
    t("en", "kb.new_generation"),
    t("ru", "kb.nanobanana_pro"),
    t("en", "kb.nanobanana_pro"),
}

def trigger_filter(message: Message) -> bool:
    text = message.text or ""
    res = text in GEN_TRIGGERS
    if not res and ("Nanobanana" in text or "Базовая" in text):
         _logger.warning("DEBUG: Filter mismatch! text='%r' not in GEN_TRIGGERS. Set has: %r", text, GEN_TRIGGERS)
    return res

@router.message(
    StateFilter("*"),
    trigger_filter
)
async def restart_generate_any_state(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    _logger.info("restart_generate_any_state triggered by text='%s'", text)
    if text in {t("ru", "kb.nanobanana_pro"), t("en", "kb.nanobanana_pro")}:
        assert _db is not None
        balance = await _db.get_token_balance(message.from_user.id)
        user = await _db.get_user(message.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
        if balance < 10:
            await message.answer(t(lang, "gen.not_enough_tokens", balance=balance, required=10))
            return
        await start_generate(message, state)
        await state.update_data(preferred_model="nano-banana-pro")
        return
    await start_generate(message, state)

def type_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=t(lang, "gen.type.text"), callback_data="gen_type:text")],
        [InlineKeyboardButton(text=t(lang, "gen.type.text_photo"), callback_data="gen_type:text_photo")],
        [InlineKeyboardButton(text=t(lang, "gen.type.text_multi"), callback_data="gen_type:text_multi")],
        [InlineKeyboardButton(text=t(lang, "gen.type.edit_photo"), callback_data="gen_type:edit_photo")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def ratio_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    labels = [
        "auto",
        "1:1",
        "9:16",
        "16:9",
        "3:4",
        "4:3",
        "3:2",
        "2:3",
        "5:4",
        "4:5",
        "21:9",
    ]
    emoji_map: dict[str, str] = {
        "1:1": "◻️",
        "9:16": "📱",
        "16:9": "📺",
        "3:4": "📱",
        "4:3": "🖼️",
        "3:2": "🖼️",
        "2:3": "📱",
        "5:4": "🖼️",
        "4:5": "📱",
        "21:9": "🎬",
    }
    rows = []
    row: list[InlineKeyboardButton] = []
    for i, label in enumerate(labels):
        if label == "auto":
            shown = f"{t(lang, 'gen.ratio.auto')} ✨"
        else:
            em = emoji_map.get(label, "📐")
            shown = f"{em} {label}"
        row.append(InlineKeyboardButton(text=shown, callback_data=f"ratio:{label}"))
        if (i + 1) % 3 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def resolution_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"2K (10 🍌)", callback_data="res:2K")],
            [InlineKeyboardButton(text=f"4K (15 🍌)", callback_data="res:4K")],
        ]
    )


def confirm_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "gen.confirm.ok"), callback_data="confirm:ok")],
            [InlineKeyboardButton(text=t(lang, "gen.confirm.cancel"), callback_data="confirm:cancel")],
        ]
    )


def post_result_reply_keyboard(lang: str | None = None) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "kb.repeat_generation"))],
            [KeyboardButton(text=t(lang, "kb.generate")), KeyboardButton(text=t(lang, "kb.nanobanana_pro"))],
            [KeyboardButton(text=t(lang, "kb.profile")), KeyboardButton(text=t(lang, "avatars.btn_label")), KeyboardButton(text=t(lang, "kb.topup"))],
        ],
        resize_keyboard=True,
    )


def photo_count_keyboard(selected: int | None = None, lang: str | None = None) -> InlineKeyboardMarkup:
    """Инлайн‑клавиатура выбора количества фото: 1–5, 6–10, затем подтверждение.
    Если число выбрано, рядом с ним показывается галочка.
    """
    rows: list[list[InlineKeyboardButton]] = []

    def btn(n: int) -> InlineKeyboardButton:
        mark = " ✅" if selected == n else ""
        return InlineKeyboardButton(text=f"{n}{mark}", callback_data=f"pc:select:{n}")

    # Первый ряд: 1–5
    rows.append([btn(1), btn(2), btn(3), btn(4), btn(5)])
    # Второй ряд: 6–10
    rows.append([btn(6), btn(7), btn(8), btn(9), btn(10)])
    # Третий ряд: подтверждение
    rows.append([InlineKeyboardButton(text=t(lang, "gen.confirm_label"), callback_data="pc:confirm")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def avatar_source_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "avatars.source_photo"), callback_data="source:photo")],
            [InlineKeyboardButton(text=t(lang, "avatars.source_avatar"), callback_data="source:avatar")],
        ]
    )


def avatar_pick_keyboard(avatars: list[dict], lang: str | None = None) -> InlineKeyboardMarkup:
    kb = []
    for a in avatars:
        name = a.get("display_name") or "Avatar"
        aid = a.get("id")
        kb.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=f"avatar:pick:{aid}")])
    kb.append([InlineKeyboardButton(text=t(lang, "avatars.source_photo"), callback_data="source:photo")])
    return InlineKeyboardMarkup(inline_keyboard=kb)



@router.message(Command("generate"))
async def start_generate(message: Message, state: FSMContext) -> None:
    assert _client is not None and _db is not None
    try:
        bot_me = await message.bot.get_me()
        bot_name = getattr(bot_me, "username", None)
        if bot_name:
            await _db.ensure_bot_subscription(int(message.from_user.id), bot_name)
            try:
                _exists = await _db.has_bot_subscription(int(message.from_user.id), bot_name)
                if not _exists:
                    await _db.ensure_bot_subscription(int(message.from_user.id), bot_name)
            except Exception:
                pass
    except Exception:
        pass

    # Проверка токенов в Supabase (баланс хранится только там)
    balance = await _db.get_token_balance(message.from_user.id)
    _logger.info("/generate start user=%s balance=%s", message.from_user.id, balance)
    if balance < 3:
        user = await _db.get_user(message.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
        await message.answer(t(lang, "gen.not_enough_tokens", balance=balance, required=3))
        _logger.warning("User %s has insufficient balance (need 3)", message.from_user.id)
        return

    await state.clear()
    await state.set_state(GenerateStates.choosing_type)
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    await state.update_data(user_id=message.from_user.id, lang=lang)
    await message.answer(
        t(lang, "gen.choose_method"),
        reply_markup=type_keyboard(lang),
    )


@router.callback_query(StateFilter(GenerateStates.choosing_type), F.data.startswith("gen_type:"))
async def choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if not data.startswith("gen_type:"):
        await callback.answer()
        return
    gen_type = data.split(":", 1)[1]
    _logger.info("User %s chose type=%s", callback.from_user.id, gen_type)
    await state.update_data(gen_type=gen_type)
    st = await state.get_data()
    lang = st.get("lang")
    # Для режима редактирования: сначала просим фото, затем текст
    if gen_type == "edit_photo":
        await state.update_data(photos_needed=1, photos=[])
        await state.set_state(GenerateStates.waiting_photos)
        await callback.message.edit_text(t(lang, "gen.upload_photo"))
        await callback.answer()
        return
    # Остальные режимы: сначала просим промпт
    await state.set_state(GenerateStates.waiting_prompt)
    await callback.message.edit_text(t(lang, "gen.enter_prompt"))
    await callback.answer()


@router.message(StateFilter(GenerateStates.waiting_prompt))
async def receive_prompt(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    st0 = await state.get_data()
    lang0 = st0.get("lang")
    gen_triggers = {
        t("ru", "kb.generate"),
        t("en", "kb.generate"),
        t("ru", "kb.new_generation"),
        t("en", "kb.new_generation"),
        t("ru", "kb.nanobanana_pro"),
        t("en", "kb.nanobanana_pro"),
    }
    non_prompt_labels = {
        t("ru", "kb.topup"),
        t("en", "kb.topup"),
        t("ru", "kb.profile"),
        t("en", "kb.profile"),
        t("ru", "kb.start"),
        t("en", "kb.start"),
        t("ru", "kb.repeat_generation"),
        t("en", "kb.repeat_generation"),
    }
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        if cmd.startswith("/generate"):
            await state.clear()
            await start_generate(message, state)
            return
        await state.clear()
        await message.answer(t(lang0, "gen.canceled"))
        return
    if text in gen_triggers:
        await state.clear()
        if text in {t("ru", "kb.nanobanana_pro"), t("en", "kb.nanobanana_pro")}:
            await start_generate(message, state)
            await state.update_data(preferred_model="nano-banana-pro")
        else:
            await start_generate(message, state)
        return
    if text in non_prompt_labels:
        await state.clear()
        await message.answer(t(lang0, "gen.canceled"))
        return
    prompt = (message.text or "").strip()
    if not prompt:
        st = await state.get_data()
        lang = st.get("lang")
        await message.answer(t(lang, "gen.prompt_empty"))
        _logger.warning("User %s sent empty prompt", message.from_user.id)
        return
    
    # Check prompt length to avoid MESSAGE_TOO_LONG error
    if len(prompt) > MAX_PROMPT_LENGTH:
        st = await state.get_data()
        lang = st.get("lang")
        await message.answer(
            f"⚠️ Ваш промпт слишком длинный ({len(prompt)} символов).\n\n"
            f"Максимальная длина в боте: {MAX_PROMPT_LENGTH} символов.\n\n"
            f"Пожалуйста, сократите текст и отправьте заново.\n\n"
            f"💡 Для генерации с длинными промптами (до 10 000 символов) "
            f"воспользуйтесь нашим приложением: @AiVerseAppBot"
        )
        _logger.warning("User %s sent too long prompt: %s chars (max %s)", message.from_user.id, len(prompt), MAX_PROMPT_LENGTH)
        return
    
    _logger.info("User %s provided prompt len=%s", message.from_user.id, len(prompt))
    await state.update_data(prompt=prompt)

    data = await state.get_data()
    gen_type = data.get("gen_type")
    lang = data.get("lang")
    if gen_type == "text":
        await state.set_state(GenerateStates.choosing_ratio)
        await message.answer(t(lang, "gen.choose_ratio"), reply_markup=ratio_keyboard(lang))
        return
    elif gen_type == "text_photo":
        # Check if user has avatars
        assert _db is not None
        avatars = await _db.list_avatars(message.from_user.id)
        if avatars:
            await state.set_state(GenerateStates.choosing_avatar)
            await message.answer(t(lang, "avatars.choose_source"), reply_markup=avatar_source_keyboard(lang))
            return

        await state.update_data(photos_needed=1, photos=[])
        await state.set_state(GenerateStates.waiting_photos)
        await message.answer(t(lang, "gen.upload_photo"))
        return
    elif gen_type == "text_multi":
        await state.set_state(GenerateStates.waiting_photo_count)
        await state.update_data(selected_photo_count=None)
        await message.answer(
            t(lang, "gen.choose_count"),
            reply_markup=photo_count_keyboard(None, lang),
        )
        _logger.info("User %s chose multi-photo mode", message.from_user.id)
        return
    elif gen_type == "edit_photo":
        # В режиме редактирования фото приходит раньше, сейчас запрашиваем подтверждение сразу,
        # пропускаем выбор соотношения и используем Auto (как у источника)
        st2 = await state.get_data()
        photos = st2.get("photos", [])
        photos_needed = st2.get("photos_needed", 1)
        ratio_label = t(lang, "gen.ratio.auto")
        await state.update_data(ratio="auto")

        type_map = {
            "text": t(lang, "gen.type.text"),
            "text_photo": t(lang, "gen.type.text_photo"),
            "text_multi": t(lang, "gen.type.text_multi"),
            "edit_photo": t(lang, "gen.type.edit_photo"),
        }
        gen_type_label = type_map.get(gen_type, str(gen_type))

        display_prompt = truncate_prompt(str(prompt or ''))
        summary = (
            f"{t(lang, 'gen.summary.title')}\n\n"
            f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
            f"{t(lang, 'gen.summary.prompt', prompt=html.bold(html.quote(display_prompt)))}\n"
            f"{t(lang, 'gen.summary.ratio', ratio=ratio_label)}\n"
        )
        summary += f"• Фото: {len(photos)} из {photos_needed}"

        await state.set_state(GenerateStates.confirming)
        await message.answer(summary, reply_markup=confirm_keyboard(lang))
        return
    else:
        await message.answer(t(lang, "gen.unknown_type"))
        await state.clear()


@router.callback_query(StateFilter(GenerateStates.choosing_avatar), F.data == "source:photo")
async def avatar_source_photo(callback: CallbackQuery, state: FSMContext) -> None:
    st = await state.get_data()
    lang = st.get("lang")
    await state.update_data(photos_needed=1, photos=[])
    await state.set_state(GenerateStates.waiting_photos)
    await callback.message.edit_text(t(lang, "gen.upload_photo"))
    await callback.answer()


@router.callback_query(StateFilter(GenerateStates.choosing_avatar), F.data == "source:avatar")
async def avatar_source_list(callback: CallbackQuery, state: FSMContext) -> None:
    assert _db is not None
    st = await state.get_data()
    lang = st.get("lang")
    items = await _db.list_avatars(callback.from_user.id)
    if not items:
        await callback.answer(t(lang, "avatars.empty"), show_alert=True)
        return
    
    await callback.message.edit_text(t(lang, "avatars.pick_hint"), reply_markup=avatar_pick_keyboard(items, lang))
    await callback.answer()


@router.callback_query(StateFilter(GenerateStates.choosing_avatar), F.data.startswith("avatar:pick:"))
async def avatar_pick(callback: CallbackQuery, state: FSMContext) -> None:
    aid = callback.data.split(":", 2)[2]
    assert _db is not None
    avatar = await _db.get_avatar(aid)
    if not avatar:
         await callback.answer("Avatar not found", show_alert=True)
         return
    
    await state.update_data(
        avatar_file_path=avatar.get("file_path"),
        avatar_display_name=avatar.get("display_name"),
        photos_needed=1,
        photos=[], 
    )
    
    st = await state.get_data()
    lang = st.get("lang")
    await state.set_state(GenerateStates.choosing_ratio)
    await callback.message.edit_text(t(lang, "gen.choose_ratio"), reply_markup=ratio_keyboard(lang))
    await callback.answer()



@router.message(StateFilter(GenerateStates.waiting_photo_count))
async def receive_photo_count(message: Message, state: FSMContext) -> None:
    # Переход на инлайн‑кнопки: если пользователь ввёл число текстом,
    # подскажем использовать кнопки.
    st = await state.get_data()
    selected = st.get("selected_photo_count")
    lang = st.get("lang")
    await message.answer(
        t(lang, "gen.use_buttons"),
        reply_markup=photo_count_keyboard(selected if isinstance(selected, int) else None, lang),
    )
    _logger.info("User %s typed while waiting_photo_count; suggested inline buttons", message.from_user.id)


@router.callback_query(StateFilter(GenerateStates.waiting_photo_count), F.data.startswith("pc:select:") | (F.data == "pc:confirm"))
async def photo_count_callbacks(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if data.startswith("pc:select:"):
        try:
            count = int(data.split(":")[-1])
        except ValueError:
            await callback.answer()
            return
        if not (1 <= count <= 10):
            await callback.answer()
            return
        await state.update_data(selected_photo_count=count)
        st = await state.get_data()
        lang = st.get("lang")
        await callback.message.edit_reply_markup(reply_markup=photo_count_keyboard(count, lang))
        await callback.answer()
        _logger.info("User %s selected photo_count=%s", callback.from_user.id, count)
        return
    elif data == "pc:confirm":
        st = await state.get_data()
        count = st.get("selected_photo_count")
        if not isinstance(count, int) or count < 1 or count > 10:
            lang = st.get("lang")
            await callback.answer(t(lang, "gen.use_buttons"), show_alert=True)
            return
        await state.update_data(photos_needed=count, photos=[])
        await state.set_state(GenerateStates.waiting_photos)
        lang = st.get("lang")
        await callback.message.edit_text(t(lang, "gen.confirmed_count", count=count))
        await callback.answer("Готово")
        _logger.info("User %s confirmed photo_count=%s", callback.from_user.id, count)
        return
    else:
        await callback.answer()
        return


@router.message(StateFilter(GenerateStates.waiting_photos), F.photo)
async def receive_photo(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = list(data.get("photos", []))
    photos_needed = int(data.get("photos_needed", 1))

    photos.append(photo_id)
    await state.update_data(photos=photos)
    _logger.info("User %s sent photo %s/%s file_id=%s", message.from_user.id, len(photos), photos_needed, photo_id)

    if len(photos) < photos_needed:
        idx = len(photos)
        st = await state.get_data()
        lang = st.get("lang")
        await message.answer(t(lang, "gen.photo_received", idx=idx, total=photos_needed, next=idx + 1))
        return

    # Все фото получены
    st = await state.get_data()
    lang = st.get("lang")
    gen_type = st.get("gen_type")
    if gen_type == "edit_photo":
        # В режиме редактирования после фото просим промпт
        await state.set_state(GenerateStates.waiting_prompt)
        await message.answer(t(lang, "gen.edit.enter_prompt"))
        return
    # Обычные режимы — выбор соотношения сторон
    await state.set_state(GenerateStates.choosing_ratio)
    await message.answer(t(lang, "gen.choose_ratio"), reply_markup=ratio_keyboard(lang))


@router.message(StateFilter(GenerateStates.waiting_photos))
async def require_photo(message: Message, state: FSMContext) -> None:
    # Если пользователь нажал «Сгенерировать 🖼️» или «Новая генерация 🆕» — начинаем заново
    text = (message.text or "").strip()
    st = await state.get_data()
    lang = st.get("lang")
    if text in {t("ru", "kb.generate"), t("en", "kb.generate"), t("ru", "kb.new_generation"), t("en", "kb.new_generation"), t("ru", "kb.nanobanana_pro"), t("en", "kb.nanobanana_pro")}:
        if text in {t("ru", "kb.nanobanana_pro"), t("en", "kb.nanobanana_pro")}:
            await start_generate(message, state)
            await state.update_data(preferred_model="nano-banana-pro")
        else:
            await start_generate(message, state)
        return
    # Если пользователь открыл главное меню или ввёл /start — не мешаем обработчику старт
    if text in {t("ru", "kb.start"), t("en", "kb.start")} or text.startswith("/start"):
        # Позволим обработчику /start очистить состояние и показать меню
        return
    photos = list(st.get("photos", []))
    photos_needed = int(st.get("photos_needed", 1))
    next_idx = min(len(photos) + 1, photos_needed)
    await message.answer(t(lang, "gen.require_photo", next=next_idx, total=photos_needed))





@router.callback_query(StateFilter(GenerateStates.choosing_ratio), F.data.startswith("ratio:"))
async def choose_ratio(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if not data.startswith("ratio:"):
        await callback.answer()
        return
    ratio = data.split(":", 1)[1]
    await state.update_data(ratio=ratio)
    _logger.info("User %s chose ratio=%s", callback.from_user.id, ratio)

    st = await state.get_data()
    gen_type = st.get("gen_type")
    prompt = st.get("prompt")
    photos = st.get("photos", [])
    photos_needed = st.get("photos_needed")
    preferred_model = st.get("preferred_model")

    st2 = await state.get_data()
    lang = st2.get("lang")

    # If NanoBanana Pro, go to resolution selection
    if preferred_model == "nano-banana-pro":
        await state.set_state(GenerateStates.choosing_resolution)
        await callback.message.edit_text(t(lang, "gen.choose_resolution"), reply_markup=resolution_keyboard(lang))
        await callback.answer()
        return

    type_map = {
        "text": t(lang, "gen.type.text"),
        "text_photo": t(lang, "gen.type.text_photo"),
        "text_multi": t(lang, "gen.type.text_multi"),
    }
    gen_type_label = type_map.get(gen_type, str(gen_type))

    display_prompt = truncate_prompt(str(prompt or ''))
    summary = (
        f"{t(lang, 'gen.summary.title')}\n\n"
        f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
        f"{t(lang, 'gen.summary.prompt', prompt=html.bold(html.quote(display_prompt)))}\n"
        f"{t(lang, 'gen.summary.ratio', ratio=ratio)}\n"
    )
    if gen_type in {"text_photo", "text_multi"}:
        if photos:
            summary += f"• Фото: {len(photos)} из {photos_needed}"
        elif st.get("avatar_display_name"):
            summary += f"• Аватар: {st.get('avatar_display_name')}"

    await state.set_state(GenerateStates.confirming)
    try:
        await callback.message.edit_text(summary, reply_markup=confirm_keyboard(lang))
    except TelegramBadRequest as e:
        if "MESSAGE_TOO_LONG" in str(e):
            _logger.warning("Summary too long for user %s, sending shortened version", callback.from_user.id)
            short_summary = (
                f"{t(lang, 'gen.summary.title')}\n\n"
                f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
                f"• Промпт: (слишком длинный для отображения)\n"
                f"{t(lang, 'gen.summary.ratio', ratio=ratio)}\n"
            )
            if gen_type in {"text_photo", "text_multi"}:
                short_summary += f"• Фото: {len(photos)} из {photos_needed}"
            await callback.message.edit_text(short_summary, reply_markup=confirm_keyboard(lang))
        else:
            raise
    await callback.answer()


@router.callback_query(StateFilter(GenerateStates.choosing_resolution), F.data.startswith("res:"))
async def choose_resolution(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if not data.startswith("res:"):
        await callback.answer()
        return
    resolution = data.split(":", 1)[1]
    await state.update_data(resolution=resolution)
    _logger.info("User %s chose resolution=%s", callback.from_user.id, resolution)

    st = await state.get_data()
    lang = st.get("lang")
    gen_type = st.get("gen_type")
    prompt = st.get("prompt")
    ratio = st.get("ratio")
    
    type_map = {
        "text": t(lang, "gen.type.text"),
        "text_photo": t(lang, "gen.type.text_photo"),
        "text_multi": t(lang, "gen.type.text_multi"),
    }
    gen_type_label = type_map.get(gen_type, str(gen_type))
    
    # Determine price based on resolution
    price = 10 if resolution == "2K" else 15
    await state.update_data(tokens_required=price)

    display_prompt = truncate_prompt(str(prompt or ''))
    summary = (
        f"{t(lang, 'gen.summary.title')}\n\n"
        f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
        f"{t(lang, 'gen.summary.prompt', prompt=html.bold(html.quote(display_prompt)))}\n"
        f"{t(lang, 'gen.summary.ratio', ratio=ratio)}\n"
        f"{t(lang, 'gen.summary.resolution', resolution=resolution, price=price)}\n"
    )

    await state.set_state(GenerateStates.confirming)
    try:
        await callback.message.edit_text(summary, reply_markup=confirm_keyboard(lang))
    except TelegramBadRequest as e:
        if "MESSAGE_TOO_LONG" in str(e):
            _logger.warning("Summary too long for user %s, sending shortened version", callback.from_user.id)
            short_summary = (
                f"{t(lang, 'gen.summary.title')}\n\n"
                f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
                f"• Промпт: (слишком длинный для отображения)\n"
                f"{t(lang, 'gen.summary.ratio', ratio=ratio)}\n"
                f"{t(lang, 'gen.summary.resolution', resolution=resolution, price=price)}\n"
            )
            await callback.message.edit_text(short_summary, reply_markup=confirm_keyboard(lang))
        else:
            raise
    await callback.answer()


@router.callback_query(StateFilter(GenerateStates.confirming), F.data.startswith("confirm:"))
async def confirm(callback: CallbackQuery, state: FSMContext) -> None:
    choice = (callback.data or "")
    if choice == "confirm:cancel":
        await state.clear()
        st = await state.get_data()
        lang = st.get("lang")
        await callback.message.edit_text(t(lang, "gen.canceled"))
        await callback.answer("Canceled")
        _logger.info("User %s canceled generation", callback.from_user.id)
        return
    if choice != "confirm:ok":
        await callback.answer()
        return

    assert _client is not None and _db is not None

    st = await state.get_data()
    user_id = int(st.get("user_id"))
    prompt = st.get("prompt")
    gen_type = st.get("gen_type")
    ratio = st.get("ratio", "auto")
    photos = st.get("photos", [])
    avatar_path = st.get("avatar_file_path")

    # Проверка токенов перед запуском (Supabase)
    preferred = str(st.get("preferred_model") or "")
    # Use stored tokens_required if available (from resolution selection), otherwise default logic
    stored_tokens = st.get("tokens_required")
    if stored_tokens:
        required_tokens = int(stored_tokens)
    else:
        required_tokens = 15 if preferred == "nano-banana-pro" else 3
        
    balance = await _db.get_token_balance(user_id)
    if balance < required_tokens:
        lang = st.get("lang")
        await callback.message.edit_text(t(lang, "gen.not_enough_tokens", balance=balance, required=required_tokens))
        await state.clear()
        await callback.answer()
        _logger.warning("User %s insufficient balance at confirm (need %s)", user_id, required_tokens)
        return

    # Трекинг генерации в Supabase
    preferred = str(st.get("preferred_model") or "")
    db_model = "nanobanana-pro" if preferred == "nano-banana-pro" else "nanobanana"
    
    # Конвертация Telegram photo file_id → доступный URL (для edit-модели и сохранения в БД)
    image_urls = []
    telegram_urls_to_upload: list[str] = []
    if len(photos) > 0:
        for pid in photos:
            try:
                f = await callback.message.bot.get_file(pid)
                # Предупреждение: это публичный URL с токеном — используйте только если доверяете провайдеру
                tg_file_url = f"https://api.telegram.org/file/bot{callback.message.bot.token}/{f.file_path}"
                image_urls.append(tg_file_url)
                telegram_urls_to_upload.append(tg_file_url)
            except Exception as e:
                _logger.warning("Failed to fetch telegram file path for %s: %s", pid, e)
    
    if avatar_path:
        try:
            signed = await _db.create_signed_url(avatar_path)
            if signed:
                image_urls.append(signed)
        except Exception as e:
            _logger.warning("Failed to sign avatar url: %s", e)

    payload_desc = f"type={gen_type}; ratio={ratio}; photos={len(photos)}; avatars={'yes' if avatar_path else 'no'}"
    generation = await _db.create_generation(
        user_id, 
        f"{prompt} [{payload_desc}]", 
        db_model,
        input_images=image_urls or None
    )
    gen_id = generation.get("id")
    _logger.info("Generation created id=%s user=%s type=%s ratio=%s photos=%s model=%s", gen_id, user_id, gen_type, ratio, len(photos), db_model)

    # Подготовка параметров KIE API
    ratio_map = {
        "1:1": "1:1",
        "3:4": "3:4",
        "4:3": "4:3",
        "9:16": "9:16",
        "16:9": "16:9",
    }
    image_size = ratio_map.get(ratio) if ratio in ratio_map else None
    preferred = str(st.get("preferred_model") or "")
    if preferred == "nano-banana-pro":
        model = "nano-banana-pro"
    else:
        model = "google/nano-banana-edit" if len(photos) > 0 else "google/nano-banana"

    # Конвертация Telegram photo file_id → доступный URL (для edit-модели)
    # image_urls уже заполнен выше
    pass

    try:
        # Сохраним точный payload запроса в кеш для последующего повтора
        try:
            if _cache and gen_id is not None:
                selected_photo_count = st.get("selected_photo_count")
                payload = {
                    "prompt": prompt,
                    "gen_type": gen_type,
                    "ratio": ratio,
                    "image_resolution": None,
                    "max_images": selected_photo_count if isinstance(selected_photo_count, int) else 1,
                    "photos": photos,
                    "avatar_file_path": st.get("avatar_file_path"),
                    "selected_avatars": st.get("selected_avatars", []),
                    "image_size": image_size,
                    "model": model,
                }
                await _cache.set_last_generation_attempt(user_id, int(gen_id), payload)
        except Exception:
            _logger.debug("Failed to store last generation payload in cache", exc_info=True)

        _logger.info("Calling KIE API for user=%s gen_id=%s model=%s size=%s images=%s", user_id, gen_id, model, image_size, len(image_urls))
        
        # Запускаем фоновую задачу загрузки в R2
        if _r2 and telegram_urls_to_upload:
             asyncio.create_task(upload_to_r2_and_update_db(int(gen_id), list(telegram_urls_to_upload), _r2, _db))

        image_url = await _client.generate_image(
            prompt=prompt,
            model=model,
            image_urls=image_urls or None,
            image_size=image_size,
            output_format="png",
            meta={"generationId": gen_id, "userId": user_id, "tokens": required_tokens},
            resolution=st.get("resolution")
        )
    except Exception as e:
        msg = str(e)
        # Особый случай: провайдер принял задачу и пришлёт результат через callback
        if "awaiting callback" in msg:
            _logger.info("Async generation accepted: user=%s gen_id=%s", user_id, gen_id)
            # Списание 3 токенов сразу после принятия задачи
            current_balance = await _db.get_token_balance(user_id)
            new_balance = max(0, int(current_balance) - required_tokens)
            await _db.set_token_balance(user_id, new_balance)
            _logger.info("Debited %s tokens (async): user=%s balance %s->%s", required_tokens, user_id, current_balance, new_balance)
            lang = st.get("lang")
            await callback.message.edit_text(t(lang, "gen.task_accepted"))
            await state.clear()
            await callback.answer("Started")
            return

        if gen_id is not None:
            await _db.mark_generation_failed(gen_id, str(e))
        
        err_str = str(e)
        
        # Ошибка контент-модерации (sensitive content / E005)
        seedream_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔥 Попробовать Seedream 4.5", url="https://t.me/seedreameditbot")]
        ])

        if "SENSITIVE_CONTENT_ERROR" in err_str or "sensitive" in err_str.lower():
            # Sensitive content - аналогично nsfw
            msg = "🚫 Система модерации отклонила запрос. Ваш текст или изображение содержит чувствительный контент. Попробуйте в другой крутой модели — Seedream 4.5 (рекомендуем для лучшего качества)"
            await callback.message.edit_text(msg, reply_markup=seedream_kb)
            _logger.warning("Generation rejected by content moderation: user=%s gen_id=%s", user_id, gen_id)
            await state.clear()
            await callback.answer()
            return
        
        if "nsfw" in err_str.lower():
            # NSFW Redirection
            msg = "🚫 Из-за политик разработчика Нейросети, модель отклонила генерацию. Попробуйте в другой крутой модели — Seedream 4.5 (рекомендуем для лучшего качества)"
            await callback.message.edit_text(msg, reply_markup=seedream_kb)
        else:
            # General error sanitization
            sanitized = err_str.replace("KIE API error:", "").replace("KIE API", "").strip()
            await callback.message.edit_text(f"Ошибка генерации: {sanitized}")

        _logger.exception("Generation failed user=%s gen_id=%s error=%s", user_id, gen_id, e)
        await state.clear()
        await callback.answer()
        return

    # Списание 3 токенов и сохранение в Supabase (синхронный случай)
    current_balance = await _db.get_token_balance(user_id)
    new_balance = max(0, int(current_balance) - required_tokens)
    await _db.set_token_balance(user_id, new_balance)
    _logger.info("Debited %s tokens (sync): user=%s balance %s->%s", required_tokens, user_id, current_balance, new_balance)

    if gen_id is not None:
        await _db.mark_generation_completed(gen_id, image_url)

    lang = st.get("lang")
    await callback.message.edit_caption(
        caption=t(lang, "gen.done_text", balance=new_balance, ratio=ratio),
    ) if callback.message.photo else await callback.message.edit_text(
        t(lang, "gen.done_text", balance=new_balance, ratio=ratio)
    )
    # Отправим изображение как документ (URLInputFile) для сохранения качества
    try:
        from urllib.parse import urlparse
        filename = "image"
        try:
            path = urlparse(str(image_url)).path
            if path:
                base = path.rsplit("/", 1)[-1]
                if base:
                    filename = base
        except Exception:
            pass
        file = URLInputFile(url=str(image_url), filename=filename)
        await callback.message.answer_document(document=file, caption=t(lang, "gen.result_caption"), reply_markup=post_result_reply_keyboard(lang))
    except Exception as e:
        _logger.warning("Failed to send document, falling back to photo: %s", e)
    await callback.message.answer_photo(photo=image_url, caption=t(lang, "gen.result_caption"), reply_markup=post_result_reply_keyboard(lang))
    await state.clear()
    _logger.info("Generation completed: user=%s gen_id=%s image_url=%s", user_id, gen_id, image_url)
    await callback.answer("Started")




# Запуск генерации по кнопке «Новая генерация»
@router.message((F.text == t("ru", "kb.new_generation")) | (F.text == t("en", "kb.new_generation")))
async def start_generate_text_new(message: Message, state: FSMContext) -> None:
    await start_generate(message, state)


async def upload_to_r2_and_update_db(generation_id: int, telegram_urls: list[str], r2_client: R2Client, db: Database) -> None:
    """
    Background task to upload images to R2 and update the database.
    """
    try:
        r2_urls = []
        updated = False
        for url in telegram_urls:
            # Check if it's a Telegram URL (we only want to re-upload those)
            if "api.telegram.org" in url:
                r2_url = await r2_client.upload_file_from_url(url)
                if r2_url:
                    r2_urls.append(r2_url)
                    updated = True
                    _logger.info("Async R2 upload success: %s -> %s", url, r2_url)
                else:
                    r2_urls.append(url) # Keep original if failed
                    _logger.warning("Async R2 upload failed for %s", url)
            else:
                r2_urls.append(url)
        
        if updated:
            await db.update_generation_input_images(generation_id, r2_urls)
            _logger.info("Updated generation %s with R2 URLs", generation_id)
            
    except Exception as e:
        _logger.error("Error in async R2 upload task for gen %s: %s", generation_id, e)


# Повтор последнего запроса генерации (любой тип, включая фото) из кеша
@router.message((F.text == t("ru", "kb.repeat_generation")) | (F.text == t("en", "kb.repeat_generation")))
async def repeat_last_generation(message: Message, state: FSMContext) -> None:
    assert _client is not None and _db is not None
    user_id = int(message.from_user.id)
    user = await _db.get_user(user_id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    pass
    origin_gen_id: int | None = None
    payload: dict | None = None
    try:
        if _cache:
            res = await _cache.get_last_generation_attempt(user_id)
            if res:
                origin_gen_id, payload = res
    except Exception:
        payload = None
    if not payload:
        await message.answer(t(lang, "gen.repeat_not_found"))
        return
    prompt = str(payload.get("prompt") or "").strip()
    gen_type = str(payload.get("gen_type") or "text").strip()
    ratio_val = str(payload.get("ratio") or "auto").strip()
    photos = payload.get("photos") or []
    type_map = {
        "text": t(lang, "gen.type.text"),
        "text_photo": t(lang, "gen.type.text_photo"),
        "text_multi": t(lang, "gen.type.text_multi"),
        "edit_photo": t(lang, "gen.type.edit_photo"),
    }
    gen_type_label = type_map.get(gen_type, str(gen_type))
    ratio_label = t(lang, "gen.ratio.auto") if ratio_val == "auto" else ratio_val
    display_prompt = truncate_prompt(str(prompt or ''))
    summary = (
        f"{t(lang, 'gen.summary.title')}\n\n"
        f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
        f"{t(lang, 'gen.summary.prompt', prompt=html.bold(html.quote(display_prompt)))}\n"
        f"{t(lang, 'gen.summary.ratio', ratio=ratio_label)}\n"
    )
    if gen_type in {"text_photo", "text_multi", "edit_photo"}:
        summary += f"• Фото: {len(photos)}"
    await state.update_data(user_id=user_id, lang=lang, repeat_origin_gen_id=origin_gen_id, repeat_payload=payload)
    await state.set_state(GenerateStates.repeating_confirm)
    await message.answer(summary, reply_markup=confirm_keyboard(lang))

@router.callback_query(StateFilter(GenerateStates.repeating_confirm), F.data.startswith("confirm:"))
async def confirm_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    choice = (callback.data or "")
    st = await state.get_data()
    lang = st.get("lang")
    if choice == "confirm:cancel":
        await state.clear()
        await callback.message.edit_text(t(lang, "gen.canceled"))
        await callback.answer("Canceled")
        return
    if choice != "confirm:ok":
        await callback.answer()
        return
    assert _client is not None and _db is not None
    user_id = int(st.get("user_id"))
    origin_gen_id = st.get("repeat_origin_gen_id")
    payload = st.get("repeat_payload") or {}
    prompt = str(payload.get("prompt") or "").strip()
    gen_type = str(payload.get("gen_type") or "text").strip()
    ratio_val = str(payload.get("ratio") or "auto").strip()
    photos = payload.get("photos") or []
    image_size = payload.get("image_size")
    model = payload.get("model") or ("google/nano-banana-edit" if photos else "google/nano-banana")
    required_tokens = 15 if model == "nano-banana-pro" else 3
    balance = await _db.get_token_balance(user_id)
    if balance < required_tokens:
        await callback.message.edit_text(t(lang, "gen.not_enough_tokens", balance=balance, required=required_tokens))
        await state.clear()
        await callback.answer()
        return
    payload_desc = f"repeat_of={origin_gen_id}; type={gen_type}; ratio={ratio_val}; photos={len(photos)}; avatars=0"
    db_model = "nanobanana-pro" if model == "nano-banana-pro" else "nanobanana"
    
    image_urls: list[str] = []
    telegram_urls_to_upload: list[str] = []

    # Try to reuse R2 URLs from original generation
    r2_urls_reused = False
    if origin_gen_id:
        try:
            origin_gen = await _db.get_generation(origin_gen_id)
            if origin_gen and origin_gen.get("input_images"):
                origin_images = origin_gen.get("input_images")
                # Check if they look like R2 URLs (or just valid URLs that are not telegram API)
                if all(isinstance(u, str) and u.startswith("http") and "api.telegram.org" not in u for u in origin_images):
                    image_urls = origin_images
                    r2_urls_reused = True
                    _logger.info("Reusing R2 URLs from gen %s for repeat", origin_gen_id)
        except Exception as e:
            _logger.warning("Failed to fetch origin generation %s: %s", origin_gen_id, e)

    if photos and not r2_urls_reused:
        for pid in photos:
            try:
                f = await callback.message.bot.get_file(pid)
                # Получаем временную ссылку от Telegram
                tg_file_url = f"https://api.telegram.org/file/bot{callback.message.bot.token}/{f.file_path}"
                image_urls.append(tg_file_url)
                telegram_urls_to_upload.append(tg_file_url)
            except Exception as e:
                _logger.warning("Failed to fetch telegram file path for %s: %s", pid, e)

    # Создаем запись в БД
    try:
        gen = await _db.create_generation(
            user_id=user_id,
            prompt=f"{prompt} [{payload_desc}]", # Adjusted prompt to match original logic
            model=db_model,
            parent_id=origin_gen_id, # Added parent_id to match original logic
            input_images=image_urls or None,
        )
        gen_id = gen.get("id")
        _logger.info("Repeat generation created id=%s user=%s type=%s ratio=%s photos=%s", gen_id, user_id, gen_type, ratio_val, len(photos))
    except Exception as e:
        _logger.error("Failed to create generation record: %s", e)
        await callback.message.edit_text(t(lang, "gen.error_db"))
        await state.clear()
        await callback.answer()
        return

    if not image_size: # This block was before the try/except for generation creation
        ratio_map = {
            "1:1": "1:1",
            "3:4": "3:4",
            "4:3": "4:3",
            "9:16": "9:16",
            "16:9": "16:9",
        }
        image_size = ratio_map.get(ratio_val) if ratio_val in ratio_map else None

    try:
        _logger.info("Calling KIE API for user=%s gen_id=%s model=%s size=%s images=%s", user_id, gen_id, model, image_size, len(image_urls))

        # Запускаем фоновую задачу загрузки в R2
        if _r2 and telegram_urls_to_upload:
             asyncio.create_task(upload_to_r2_and_update_db(int(gen_id), list(telegram_urls_to_upload), _r2, _db))

        image_url = await _client.generate_image(
            prompt=prompt,
            model=model,
            image_urls=image_urls or None,
            image_size=image_size,
            output_format="png",
            meta={"generationId": gen_id, "userId": user_id, "tokens": required_tokens},
        )
    except Exception as e:
        msg = str(e)
        if "awaiting callback" in msg:
            current_balance = await _db.get_token_balance(user_id)
            new_balance = max(0, int(current_balance) - required_tokens)
            await _db.set_token_balance(user_id, new_balance)
            _logger.info("Debited %s tokens (async repeat): user=%s balance %s->%s", required_tokens, user_id, current_balance, new_balance)
            await callback.message.edit_text(t(lang, "gen.task_accepted"))
            await state.clear()
            await callback.answer("Started")
            return
        if gen_id is not None:
            await _db.mark_generation_failed(gen_id, str(e))
        await callback.message.edit_text(f"Ошибка генерации: {e}")
        _logger.exception("Repeat generation failed user=%s gen_id=%s error=%s", user_id, gen_id, e)
        await state.clear()
        await callback.answer()
        return
    current_balance = await _db.get_token_balance(user_id)
    new_balance = max(0, int(current_balance) - required_tokens)
    await _db.set_token_balance(user_id, new_balance)
    _logger.info("Debited %s tokens (sync repeat): user=%s balance %s->%s", required_tokens, user_id, current_balance, new_balance)
    if gen_id is not None:
        await _db.mark_generation_completed(gen_id, image_url)
    await callback.message.edit_caption(
        caption=t(lang, "gen.done_text", balance=new_balance, ratio=ratio_val),
    ) if callback.message.photo else await callback.message.edit_text(
        t(lang, "gen.done_text", balance=new_balance, ratio=ratio_val)
    )
    try:
        from urllib.parse import urlparse
        filename = "image"
        try:
            path = urlparse(str(image_url)).path
            if path:
                base = path.rsplit("/", 1)[-1]
                if base:
                    filename = base
        except Exception:
            pass
        file = URLInputFile(url=str(image_url), filename=filename)
        await callback.message.answer_document(document=file, caption=t(lang, "gen.result_caption"), reply_markup=post_result_reply_keyboard(lang))
    except Exception as e_doc:
        _logger.warning("Failed to send document, falling back to photo: %s", e_doc)
    await callback.message.answer_photo(photo=image_url, caption=t(lang, "gen.result_caption"), reply_markup=post_result_reply_keyboard(lang))
    await state.clear()
    _logger.info("Repeat generation completed: user=%s gen_id=%s image_url=%s", user_id, gen_id, image_url)
    await callback.answer("Started")
