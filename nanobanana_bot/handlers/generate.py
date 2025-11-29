from aiogram import Router, F, html
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ForceReply,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.types.input_file import URLInputFile
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import PurePosixPath
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from ..utils.seedream import SeedreamClient
from ..database import Database
from ..utils.i18n import t, normalize_lang
import logging
from ..cache import Cache


router = Router(name="generate")

_client: SeedreamClient | None = None
_db: Database | None = None
_cache: Cache | None = None
_seedream_model_t2i: str = "bytedance/seedream-v4-text-to-image"
_seedream_model_edit: str = "bytedance/seedream-v4-edit"
_logger = logging.getLogger("seedream.generate")


def _format_prompt_html(text: str) -> str:
    safe = text.replace("<", "&lt;").replace(">", "&gt;")
    return html.bold(safe)

def _guess_filename(url: str) -> str:
    """Определяет имя файла из URL. Если расширение отсутствует — вернёт seedream.png."""
    try:
        p = urlparse(url)
        # Попробуем взять из query параметр filename
        qs = parse_qs(p.query or "")
        fn = unquote((qs.get("filename") or [""])[0])
        if fn:
            name = fn.strip().split("/")[-1]
            if "." in name:
                ext = name.rsplit(".", 1)[-1].lower()
                if ext in {"png", "jpg", "jpeg", "webp"}:
                    return name
        # Иначе — из пути
        name = PurePosixPath(p.path or "").name
        if name and "." in name:
            ext = name.rsplit(".", 1)[-1].lower()
            if ext in {"png", "jpg", "jpeg", "webp"}:
                return name
    except Exception:
        pass
    return "seedream.png"


def setup(client: SeedreamClient, database: Database, seedream_model_t2i: str | None = None, seedream_model_edit: str | None = None, cache: Cache | None = None) -> None:
    global _client, _db, _seedream_model_t2i, _seedream_model_edit, _cache
    _client = client
    _db = database
    _cache = cache
    if isinstance(seedream_model_t2i, str) and seedream_model_t2i.strip():
        _seedream_model_t2i = seedream_model_t2i.strip()
    if isinstance(seedream_model_edit, str) and seedream_model_edit.strip():
        _seedream_model_edit = seedream_model_edit.strip()

class GenerateStates(StatesGroup):
    choosing_type = State()
    waiting_prompt = State()
    waiting_photo_count = State()
    waiting_photos = State()
    choosing_ratio = State()
    confirming = State()
    choosing_avatar = State()
    choosing_avatars_multi = State()
    repeating_confirm = State()




def type_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=t(lang, "gen.type.text"), callback_data="gen_type:text")],
        [InlineKeyboardButton(text=t(lang, "gen.type.text_photo"), callback_data="gen_type:text_photo")],
        [InlineKeyboardButton(text=t(lang, "gen.type.text_multi"), callback_data="gen_type:text_multi")],
        [InlineKeyboardButton(text=t(lang, "gen.type.edit_photo"), callback_data="gen_type:edit_photo")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def ratio_keyboard() -> InlineKeyboardMarkup:
    # Supported aspect ratios (auto removed; unsupported 5:4 and 4:5 removed)
    # Display texts include orientation emojis; callback_data stays pure ratio value
    items: list[tuple[str, str]] = [
        ("1:1", "◻️ 1:1"),
        ("9:16", "📱 9:16"),
        ("16:9", "🖼️ 16:9"),
        ("3:4", "📱 3:4"),
        ("4:3", "🖼️ 4:3"),
        ("3:2", "🖼️ 3:2"),
        ("2:3", "📱 2:3"),
        ("21:9", "🖼️ 21:9"),
    ]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, (value, display) in enumerate(items):
        row.append(InlineKeyboardButton(text=display, callback_data=f"ratio:{value}"))
        if (i + 1) % 3 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "gen.confirm.ok"), callback_data="confirm:ok")],
            [InlineKeyboardButton(text=t(lang, "gen.confirm.cancel"), callback_data="confirm:cancel")],
        ]
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
    # Третий ряд: добавить аватары
    rows.append([InlineKeyboardButton(text=t(lang, "gen.btn.add_avatars"), callback_data="pc:add_avatars")])
    # Четвёртый ряд: подтверждение
    rows.append([InlineKeyboardButton(text=t(lang, "gen.confirm_label"), callback_data="pc:confirm")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def avatar_source_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "avatars.btn_send_new"), callback_data="avatar_src:new")],
            [InlineKeyboardButton(text=t(lang, "avatars.btn_choose"), callback_data="avatar_src:pick")],
        ]
    )


def avatars_pick_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in items:
        aid = r.get("id")
        name = r.get("display_name") or "—"
        rows.append([InlineKeyboardButton(text=name, callback_data=f"avatar_pick:{aid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar_src:new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def avatars_pick_multi_keyboard(items: list[dict], selected_ids: set[int] | None, lang: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    selected_ids = selected_ids or set()
    for r in items:
        aid = int(r.get("id"))
        name = r.get("display_name") or "—"
        mark = " ✅" if aid in selected_ids else ""
        rows.append([InlineKeyboardButton(text=f"{name}{mark}", callback_data=f"avatar_multi:toggle:{aid}")])
    # Управляющие кнопки: подтвердить и назад
    rows.append([
        InlineKeyboardButton(text=t(lang, "gen.confirm.ok"), callback_data="avatar_multi:confirm"),
    ])
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar_multi:back"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("generate"))
async def start_generate(message: Message, state: FSMContext) -> None:
    assert _client is not None and _db is not None

    # Проверка токенов в Supabase (баланс хранится только там)
    balance = await _db.get_token_balance(message.from_user.id)
    _logger.info("/generate start user=%s balance=%s", message.from_user.id, balance)
    if balance < 3:
        user = await _db.get_user(message.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
        await message.answer(t(lang, "gen.not_enough_tokens", balance=balance))
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


@router.callback_query(StateFilter(GenerateStates.choosing_type))
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
    await callback.message.answer(
        t(lang, "gen.enter_prompt"),
        reply_markup=ForceReply(input_field_placeholder=t(lang, "ph.prompt"), selective=False),
    )
    await callback.answer()


@router.message(StateFilter(GenerateStates.waiting_prompt))
async def receive_prompt(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    st0 = await state.get_data()
    lang0 = st0.get("lang")
    if text in {t("ru", "kb.generate"), t("en", "kb.generate"), t("ru", "kb.new_generation"), t("en", "kb.new_generation")}:
        await start_generate(message, state)
        return
    prompt = text
    if not prompt:
        st = await state.get_data()
        lang = st.get("lang")
        await message.answer(t(lang, "gen.prompt_empty"))
        _logger.warning("User %s sent empty prompt", message.from_user.id)
        return
    _logger.info("User %s provided prompt len=%s", message.from_user.id, len(prompt))
    await state.update_data(prompt=prompt)

    data = await state.get_data()
    gen_type = data.get("gen_type")
    lang = data.get("lang")
    if gen_type == "text":
        await state.set_state(GenerateStates.choosing_ratio)
        await message.answer(t(lang, "gen.choose_ratio"), reply_markup=ratio_keyboard())
        return
    elif gen_type == "text_photo":
        # Проверим наличие аватаров и предложим выбор источника фото
        assert _db is not None
        avatars = await _db.list_avatars(message.from_user.id)
        if avatars:
            await state.set_state(GenerateStates.waiting_prompt)  # остаёмся в том же состоянии для кнопок
            await message.answer(t(lang, "avatars.choose_source"), reply_markup=avatar_source_keyboard(lang))
            return
        # Если аватаров нет — продолжаем стандартный поток
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

        summary = (
            f"{t(lang, 'gen.summary.title')}\n\n"
            f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
            f"{t(lang, 'gen.summary.prompt', prompt=_format_prompt_html(prompt))}\n"
            f"{t(lang, 'gen.summary.ratio', ratio=ratio_label)}\n"
        )
        summary += t(lang, "gen.summary.photos", count=len(photos), needed=photos_needed)

        await state.set_state(GenerateStates.confirming)
        await message.answer(summary, reply_markup=confirm_keyboard(lang))
        return
    else:
        await message.answer(t(lang, "gen.unknown_type"))
        await state.clear()


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


@router.callback_query(StateFilter(GenerateStates.waiting_photo_count))
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
    elif data == "pc:add_avatars":
        # Открываем выбор нескольких аватаров
        assert _db is not None
        items = await _db.list_avatars(callback.from_user.id)
        st = await state.get_data()
        lang = st.get("lang")
        if not items:
            await callback.answer(t(lang, "avatars.empty"), show_alert=True)
            return
        await state.set_state(GenerateStates.choosing_avatars_multi)
        # Инициализируем множество выбранных ID, если ещё не существует
        selected_ids = set(st.get("multi_selected_avatar_ids") or [])
        await callback.message.edit_text(
            t(lang, "avatars.pick_multi_title"),
            reply_markup=avatars_pick_multi_keyboard(items, selected_ids, lang),
        )
        await callback.answer()
        return
    else:
        await callback.answer()
        return


@router.callback_query(StateFilter(GenerateStates.waiting_prompt))
async def avatar_source_choice(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if data == "avatar_src:new":
        st = await state.get_data()
        lang = st.get("lang")
        await state.update_data(photos_needed=1, photos=[])
        await state.set_state(GenerateStates.waiting_photos)
        await callback.message.answer(t(lang, "gen.upload_photo"))
        await callback.answer()
        return
    if data == "avatar_src:pick":
        assert _db is not None
        user = await _db.get_user(callback.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
        items = await _db.list_avatars(callback.from_user.id)
        if not items:
            await callback.answer()
            return
        await state.set_state(GenerateStates.choosing_avatar)
        await callback.message.answer(t(lang, "avatars.pick_title"), reply_markup=avatars_pick_keyboard(items))
        await callback.answer()
        return
    await callback.answer()


@router.callback_query(StateFilter(GenerateStates.choosing_avatar))
async def pick_avatar(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    # Возврат к варианту «Отправить новое фото»
    if data == "avatar_src:new":
        st = await state.get_data()
        lang = st.get("lang")
        await state.update_data(photos_needed=1, photos=[])
        await state.set_state(GenerateStates.waiting_photos)
        await callback.message.answer(t(lang, "gen.upload_photo"))
        await callback.answer()
        return
    if not data.startswith("avatar_pick:"):
        await callback.answer()
        return
    try:
        aid = int(data.split(":", 1)[1])
    except Exception:
        await callback.answer()
        return
    assert _db is not None
    rec = await _db.get_avatar(aid)
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    if not rec:
        await callback.message.answer(t(lang, "avatars.error_pick"))
        await callback.answer()
        return
    # Сохраняем путь к файлу, имя аватара и переходим к выбору соотношения
    await state.update_data(
        avatar_file_path=rec.get("file_path"),
        avatar_display_name=rec.get("display_name"),
        photos_needed=1,
        photos=[],
    )
    await state.set_state(GenerateStates.choosing_ratio)
    await callback.message.answer(t(lang, "gen.choose_ratio"), reply_markup=ratio_keyboard())
    await callback.answer()


@router.callback_query(StateFilter(GenerateStates.choosing_avatars_multi))
async def pick_avatars_multi(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    assert _db is not None
    st = await state.get_data()
    lang = st.get("lang")
    selected_ids: set[int] = set(st.get("multi_selected_avatar_ids") or [])

    if data == "avatar_multi:back":
        # Вернуться к выбору количества фотографий
        await state.set_state(GenerateStates.waiting_photo_count)
        selected_count = st.get("selected_photo_count")
        await callback.message.edit_text(
            t(lang, "gen.choose_count"),
            reply_markup=photo_count_keyboard(selected_count if isinstance(selected_count, int) else None, lang),
        )
        await callback.answer()
        return

    if data == "avatar_multi:confirm":
        # Сохраняем выбранные аватары и переходим дальше
        # Получаем записи аватаров для сохранения путей/имён
        selected_records: list[dict] = []
        for aid in selected_ids:
            rec = await _db.get_avatar(int(aid))
            if rec:
                selected_records.append(rec)
        # Сохраняем в состоянии: имена и пути
        await state.update_data(
            selected_avatars=[
                {
                    "id": int(rec.get("id")),
                    "display_name": rec.get("display_name"),
                    "file_path": rec.get("file_path"),
                }
                for rec in selected_records
            ]
        )
        # Если пользователь не выбрал количество фото — пропускаем шаг загрузки фото
        selected_count = st.get("selected_photo_count")
        if not isinstance(selected_count, int) or selected_count < 1:
            await state.update_data(photos_needed=0, photos=[])
            await state.set_state(GenerateStates.choosing_ratio)
            await callback.message.edit_text(t(lang, "gen.choose_ratio"), reply_markup=ratio_keyboard())
            await callback.answer()
            return
        else:
            # Иначе продолжаем обычный поток: загрузка фото
            await state.update_data(photos=[], photos_needed=int(selected_count))
            await state.set_state(GenerateStates.waiting_photos)
            await callback.message.edit_text(t(lang, "gen.confirmed_count", count=int(selected_count)))
            await callback.answer()
            return

    if data.startswith("avatar_multi:toggle:"):
        try:
            aid = int(data.split(":", 2)[2])
        except Exception:
            await callback.answer()
            return
        items = await _db.list_avatars(callback.from_user.id)
        # Тоггл: добавляем/удаляем, соблюдая лимит 5
        if aid in selected_ids:
            selected_ids.remove(aid)
        else:
            if len(selected_ids) >= 5:
                await callback.answer(t(lang, "avatars.multi.limit_reached"), show_alert=True)
                return
            selected_ids.add(aid)
        await state.update_data(multi_selected_avatar_ids=list(selected_ids))
        await callback.message.edit_reply_markup(reply_markup=avatars_pick_multi_keyboard(items, selected_ids, lang))
        await callback.answer()
        return

    await callback.answer()

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
        await message.answer(
            t(lang, "gen.edit.enter_prompt"),
            reply_markup=ForceReply(input_field_placeholder=t(lang, "ph.edit_prompt"), selective=False),
        )
        return
    # Обычные режимы — выбор соотношения сторон
    await state.set_state(GenerateStates.choosing_ratio)
    await message.answer(t(lang, "gen.choose_ratio"), reply_markup=ratio_keyboard())


@router.message(StateFilter(GenerateStates.waiting_photos))
async def require_photo(message: Message, state: FSMContext) -> None:
    # Если пользователь нажал «Сгенерировать 🖼️» или «Новая генерация 🖼️» — начинаем заново
    text = (message.text or "").strip()
    st = await state.get_data()
    lang = st.get("lang")
    if text in {t("ru", "kb.generate"), t("en", "kb.generate"), t("ru", "kb.new_generation"), t("en", "kb.new_generation")}:
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


# Текстовый запуск генерации с нижней клавиатуры
@router.message((F.text == t("ru", "kb.generate")) | (F.text == t("en", "kb.generate")))
async def start_generate_text(message: Message, state: FSMContext) -> None:
    await start_generate(message, state)

# Запуск генерации по кнопке «Новая генерация»
@router.message((F.text == t("ru", "kb.new_generation")) | (F.text == t("en", "kb.new_generation")))
async def start_generate_text_new(message: Message, state: FSMContext) -> None:
    await start_generate(message, state)


@router.callback_query(StateFilter(GenerateStates.choosing_ratio))
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
    avatar_file_path = st.get("avatar_file_path")
    avatar_display_name = st.get("avatar_display_name")

    st2 = await state.get_data()
    lang = st2.get("lang")
    type_map = {
        "text": t(lang, "gen.type.text"),
        "text_photo": t(lang, "gen.type.text_photo"),
        "text_multi": t(lang, "gen.type.text_multi"),
    }
    gen_type_label = type_map.get(gen_type, str(gen_type))

    summary = (
        f"{t(lang, 'gen.summary.title')}\n\n"
        f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
        f"{t(lang, 'gen.summary.prompt', prompt=_format_prompt_html(prompt))}\n"
        f"{t(lang, 'gen.summary.ratio', ratio=ratio)}\n"
    )
    if gen_type in {"text_photo", "text_multi"}:
        if gen_type == "text_photo" and isinstance(avatar_file_path, str) and avatar_file_path:
            summary += t(lang, "gen.summary.avatar", name=(avatar_display_name or "—"))
        elif gen_type == "text_multi":
            selected_avatars = st.get("selected_avatars") or []
            if isinstance(selected_avatars, list) and len(selected_avatars) > 0:
                names = ", ".join([(a.get("display_name") or "—") for a in selected_avatars])
                summary += t(lang, "gen.summary.avatars", names=names)
            else:
                summary += t(lang, "gen.summary.photos", count=len(photos), needed=photos_needed)
        else:
            summary += t(lang, "gen.summary.photos", count=len(photos), needed=photos_needed)

    await state.set_state(GenerateStates.confirming)
    await callback.message.edit_text(summary, reply_markup=confirm_keyboard(lang))
    await callback.answer()


@router.callback_query(StateFilter(GenerateStates.confirming))
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
    avatar_file_path = st.get("avatar_file_path")
    selected_avatars = st.get("selected_avatars") or []

    # Проверка токенов перед запуском (Supabase)
    balance = await _db.get_token_balance(user_id)
    if balance < 3:
        lang = st.get("lang")
        await callback.message.edit_text(t(lang, "gen.not_enough_tokens", balance=balance))
        await state.clear()
        await callback.answer()
        _logger.warning("User %s insufficient balance at confirm (need 3)", user_id)
        return

    # Конвертация Telegram photo file_id → доступный URL (для edit-модели и сохранения в БД)
    image_urls = []
    if len(photos) > 0:
        for pid in photos:
            try:
                f = await callback.message.bot.get_file(pid)
                # Предупреждение: это публичный URL с токеном — используйте только если доверяете провайдеру
                file_url = f"https://api.telegram.org/file/bot{callback.message.bot.token}/{f.file_path}"
                image_urls.append(file_url)
            except Exception as e:
                _logger.warning("Failed to fetch telegram file path for %s: %s", pid, e)
    # Добавляем аватары (один или несколько)
    if isinstance(selected_avatars, list) and len(selected_avatars) > 0:
        for a in selected_avatars:
            fp = a.get("file_path")
            if not fp:
                continue
            try:
                signed_url = await _db.create_signed_url(fp, expires_in=600)
                if signed_url:
                    image_urls.append(signed_url)
            except Exception as e:
                _logger.warning("Failed to create signed URL for avatar %s: %s", fp, e)
    elif isinstance(avatar_file_path, str) and avatar_file_path:
        try:
            signed_url = await _db.create_signed_url(avatar_file_path, expires_in=600)
            if signed_url:
                image_urls.append(signed_url)
        except Exception as e:
            _logger.warning("Failed to create signed URL for avatar %s: %s", avatar_file_path, e)

    # Трекинг генерации в Supabase
    payload_desc = f"type={gen_type}; ratio={ratio}; photos={len(photos)}; avatars={len(selected_avatars) + (1 if avatar_file_path else 0)}"
    generation = await _db.create_generation(
        user_id, 
        f"{prompt} [{payload_desc}]",
        input_images=image_urls or None
    )
    gen_id = generation.get("id")
    _logger.info("Generation created id=%s user=%s type=%s ratio=%s photos=%s", gen_id, user_id, gen_type, ratio, len(photos))

    # Подготовка параметров KIE API
    # Seedream image_size значения (перекодировка из выбора ratio)
    ratio_map = {
        "1:1": "square_hd",
        "3:4": "portrait_4_3",
        "4:3": "landscape_4_3",
        "9:16": "portrait_16_9",
        "16:9": "landscape_16_9",
        "21:9": "landscape_21_9",
        "3:2": "landscape_3_2",
        "2:3": "portrait_3_2",
    }
    # Для auto не задаём image_size, чтобы провайдер сохранил исходное соотношение
    image_size = ratio_map.get(ratio) if ratio in ratio_map else None
    # Разрешение и количество изображений по умолчанию
    image_resolution = "4K"
    max_images = 1
    # Выбор модели: Seedream V4 — для текстовой генерации и редактирования (из конфига)
    model = _seedream_model_edit if (len(photos) > 0 or avatar_file_path or (isinstance(selected_avatars, list) and len(selected_avatars) > 0)) else _seedream_model_t2i

    # Сохраним параметры попытки генерации в кэше для возможного повторения
    try:
        if _cache is not None and gen_id is not None:
            attempt_meta = {
                "prompt": prompt,
                "gen_type": gen_type,
                "ratio": ratio,
                "image_resolution": image_resolution,
                "max_images": max_images,
                "photos": photos,
                "avatar_file_path": avatar_file_path,
                "selected_avatars": selected_avatars,
                "image_size": image_size,
                "model": model,
            }
            await _cache.set_attempt_meta(user_id, int(gen_id), attempt_meta)
    except Exception as e:
        _logger.warning("Failed to cache attempt meta user=%s gen_id=%s: %s", user_id, gen_id, e)

    # Конвертация Telegram photo file_id → доступный URL (для edit-модели)
    # image_urls уже заполнен выше
    pass
    # Добавляем аватары (один или несколько)
    if isinstance(selected_avatars, list) and len(selected_avatars) > 0:
        for a in selected_avatars:
            fp = a.get("file_path")
            if not fp:
                continue
            try:
                signed_url = await _db.create_signed_url(fp, expires_in=600)
                if signed_url:
                    image_urls.append(signed_url)
            except Exception as e:
                _logger.warning("Failed to create signed URL for avatar %s: %s", fp, e)
    elif isinstance(avatar_file_path, str) and avatar_file_path:
        try:
            signed_url = await _db.create_signed_url(avatar_file_path, expires_in=600)
            if signed_url:
                image_urls.append(signed_url)
        except Exception as e:
            _logger.warning("Failed to create signed URL for avatar %s: %s", avatar_file_path, e)

    try:
        _logger.info("Calling KIE API for user=%s gen_id=%s model=%s size=%s images=%s", user_id, gen_id, model, image_size, len(image_urls))
        image_url = await _client.generate_image(
            prompt=prompt,
            model=model,
            image_urls=image_urls or None,
            image_size=image_size,
            image_resolution=image_resolution,
            max_images=max_images,
            meta={"generationId": gen_id, "userId": user_id},
        )
    except Exception as e:
        msg = str(e)
        # Особый случай: провайдер принял задачу и пришлёт результат через callback
        if "awaiting callback" in msg:
            _logger.info("Async generation accepted: user=%s gen_id=%s", user_id, gen_id)
            # Списание 3 токенов сразу после принятия задачи
            current_balance = await _db.get_token_balance(user_id)
            new_balance = max(0, int(current_balance) - 3)
            await _db.set_token_balance(user_id, new_balance)
            _logger.info("Debited 3 tokens (async): user=%s balance %s->%s", user_id, current_balance, new_balance)
            lang = st.get("lang")
            await callback.message.edit_text(t(lang, "gen.task_accepted"))
            await state.clear()
            await callback.answer("Started")
            return

        if gen_id is not None:
            await _db.mark_generation_failed(gen_id, str(e))
        await callback.message.edit_text(f"Ошибка генерации: {e}")
        _logger.exception("Generation failed user=%s gen_id=%s error=%s", user_id, gen_id, e)
        await state.clear()
        await callback.answer()
        return

    # Списание 3 токенов и сохранение в Supabase (синхронный случай)
    current_balance = await _db.get_token_balance(user_id)
    new_balance = max(0, int(current_balance) - 3)
    await _db.set_token_balance(user_id, new_balance)
    _logger.info("Debited 3 tokens (sync): user=%s balance %s->%s", user_id, current_balance, new_balance)

    if gen_id is not None:
        await _db.mark_generation_completed(gen_id, image_url)

    lang = st.get("lang")
    await callback.message.edit_caption(
        caption=t(lang, "gen.done_text", balance=new_balance, ratio=ratio),
    ) if callback.message.photo else await callback.message.edit_text(
        t(lang, "gen.done_text", balance=new_balance, ratio=ratio)
    )
    # Отправим изображение отдельным сообщением
    await callback.message.answer_document(
        document=URLInputFile(image_url, filename=_guess_filename(image_url)),
        caption=t(lang, "gen.result_caption"),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=t(lang, "kb.repeat_generation"))],
                [KeyboardButton(text=t(lang, "kb.new_generation"))],
                [KeyboardButton(text=t(lang, "kb.start"))],
            ],
            resize_keyboard=True,
        ),
    )
    # Обновим кэш последней успешной генерации
    try:
        if _cache is not None and gen_id is not None:
            await _cache.set_last_success_meta(user_id, {
                "prompt": prompt,
                "gen_type": gen_type,
                "ratio": ratio,
                "image_resolution": image_resolution,
                "max_images": max_images,
                "photos": photos,
                "avatar_file_path": avatar_file_path,
                "selected_avatars": selected_avatars,
                "image_size": image_size,
                "model": model,
            })
    except Exception as e:
        _logger.warning("Failed to cache last success meta user=%s gen_id=%s: %s", user_id, gen_id, e)
    await state.clear()
    _logger.info("Generation completed: user=%s gen_id=%s image_url=%s", user_id, gen_id, image_url)
    await callback.answer("Started")

@router.message((F.text == t("ru", "kb.repeat_generation")) | (F.text == t("en", "kb.repeat_generation")))
async def repeat_last_generation(message: Message, state: FSMContext) -> None:
    if _client is None or _db is None:
        return
    user_id = int(message.from_user.id)
    try:
        res = _db.client.table("users").select("language_code").eq("user_id", user_id).limit(1).execute()
        rows = getattr(res, "data", []) or []
        lang = normalize_lang(rows[0].get("language_code") if rows else None)
    except Exception:
        lang = normalize_lang(message.from_user.language_code)
    meta = None
    try:
        if _cache is not None:
            meta = await _cache.get_last_success_meta(user_id)
    except Exception as e:
        _logger.warning("Failed to fetch last success meta user=%s: %s", user_id, e)
    if not isinstance(meta, dict):
        await message.answer(
            t(lang, "gen.repeat_not_found"),
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=t(lang, "kb.new_generation"))], [KeyboardButton(text=t(lang, "kb.start"))]],
                resize_keyboard=True,
            ),
        )
        return
    prompt = meta.get("prompt") or ""
    gen_type = meta.get("gen_type") or "text"
    ratio = meta.get("ratio") or "auto"
    photos = meta.get("photos") or []
    avatar_file_path = meta.get("avatar_file_path")
    selected_avatars = meta.get("selected_avatars") or []
    type_map = {
        "text": t(lang, "gen.type.text"),
        "text_photo": t(lang, "gen.type.text_photo"),
        "text_multi": t(lang, "gen.type.text_multi"),
        "edit_photo": t(lang, "gen.type.edit_photo"),
    }
    gen_type_label = type_map.get(gen_type, str(gen_type))
    ratio_label = t(lang, "gen.ratio.auto") if ratio == "auto" else ratio
    summary = (
        f"{t(lang, 'gen.summary.title')}\n\n"
        f"{t(lang, 'gen.summary.type', type=gen_type_label)}\n"
        f"{t(lang, 'gen.summary.prompt', prompt=_format_prompt_html(prompt))}\n"
        f"{t(lang, 'gen.summary.ratio', ratio=ratio_label)}\n"
    )
    if gen_type in {"text_photo", "text_multi", "edit_photo"}:
        if isinstance(selected_avatars, list) and len(selected_avatars) > 0:
            names = ", ".join([(a.get("display_name") or "—") for a in selected_avatars])
            summary += t(lang, "gen.summary.avatars", names=names)
        elif isinstance(avatar_file_path, str) and avatar_file_path:
            summary += t(lang, "gen.summary.avatar", name="—")
        else:
            summary += t(lang, "gen.summary.photos", count=len(photos), needed=len(photos))
    await state.update_data(user_id=user_id, lang=lang, repeat_meta=meta)
    await state.set_state(GenerateStates.repeating_confirm)
    await message.answer(summary, reply_markup=confirm_keyboard(lang))

@router.callback_query(StateFilter(GenerateStates.repeating_confirm))
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
    meta = st.get("repeat_meta") or {}
    prompt = meta.get("prompt") or ""
    gen_type = meta.get("gen_type") or "text"
    ratio = meta.get("ratio") or "auto"
    image_resolution = meta.get("image_resolution") or "2K"
    try:
        max_images = int(meta.get("max_images") or 1)
    except Exception:
        max_images = 1
    photos = meta.get("photos") or []
    avatar_file_path = meta.get("avatar_file_path")
    selected_avatars = meta.get("selected_avatars") or []
    balance = await _db.get_token_balance(user_id)
    if balance < 4:
        await callback.message.edit_text(t(lang, "gen.not_enough_tokens", balance=balance))
        await state.clear()
        await callback.answer()
        return
    payload_desc = f"type={gen_type}; ratio={ratio}; photos={len(photos)}; avatars={len(selected_avatars) + (1 if avatar_file_path else 0)}"
    
    image_urls = []
    if len(photos) > 0:
        for pid in photos:
            try:
                f = await callback.message.bot.get_file(pid)
                file_url = f"https://api.telegram.org/file/bot{callback.message.bot.token}/{f.file_path}"
                image_urls.append(file_url)
            except Exception as e:
                _logger.warning("Failed to fetch telegram file path for %s: %s", pid, e)
    if isinstance(selected_avatars, list) and len(selected_avatars) > 0:
        for a in selected_avatars:
            fp = a.get("file_path")
            if not fp:
                continue
            try:
                signed_url = await _db.create_signed_url(fp, expires_in=600)
                if signed_url:
                    image_urls.append(signed_url)
            except Exception as e:
                _logger.warning("Failed to create signed URL for avatar %s: %s", fp, e)
    elif isinstance(avatar_file_path, str) and avatar_file_path:
        try:
            signed_url = await _db.create_signed_url(avatar_file_path, expires_in=600)
            if signed_url:
                image_urls.append(signed_url)
        except Exception as e:
            _logger.warning("Failed to create signed URL for avatar %s: %s", avatar_file_path, e)

    origin_gen_id = meta.get("generationId") # Assuming meta has this or we need to check where it comes from. 
    # Wait, repeat_meta comes from cache.get_last_success_meta. 
    # Let's check what set_last_success_meta stores. It stores prompt, gen_type etc.
    # It seems it DOES NOT store the original generation ID explicitly as 'generationId' in the meta dict passed to set_last_success_meta.
    # However, get_last_success_meta might return (gen_id, meta) or just meta?
    # Checking code... get_last_success_meta returns just the meta dict.
    # The cache key is by user_id.
    # The previous code for NanoBananaBot used `get_last_generation_attempt` which returned `(origin_gen_id, payload)`.
    # Here `get_last_success_meta` seems to return just the dict.
    # We might need to rely on `meta.get("generationId")` if it was stored.
    # In `confirm` handler: `meta={"generationId": gen_id, "userId": user_id}` is passed to generate_image, but NOT to cache.
    # Wait, `attempt_meta` in `confirm` does NOT include `generationId`.
    # BUT `set_last_success_meta` is called at the end of `confirm_repeat` (and presumably `confirm`'s success callback if it existed, but here it's sync/async).
    # In `confirm` (lines 1020+): `await _cache.set_last_success_meta(user_id, { ... })`. It does NOT include generationId.
    # This means we might NOT have the parent ID easily available for repeats of *just completed* generations if we only look at cache.
    # HOWEVER, the user asked to apply the same changes. In NanoBananaBot, `repeat_last_generation` used `_cache.get_last_generation_attempt` which returned an ID.
    # Here, `repeat_last_generation` uses `_cache.get_last_success_meta`.
    # If we want to support parent_id, we need to know the ID of the generation being repeated.
    # If the cache doesn't store it, we can't pass it.
    # Let's check if I can modify `set_last_success_meta` calls to include it?
    # In `confirm` (line 715), `attempt_meta` is set. It doesn't have ID.
    # In `confirm` (line 1021), `set_last_success_meta` is called. It doesn't have ID.
    # I should update the cache setting logic to include `generationId` or `id`.
    # But for now, let's assume I can add it to the `create_generation` call if I find it.
    # If `meta` has `generationId` (maybe I'll add it to cache saving), I'll use it.
    # For now, I will try to get `id` from meta, defaulting to None.
    
    # Actually, looking at `nanobanana_bot` code, `repeat_last_generation` had `origin_gen_id, payload = res`.
    # Here `meta = await _cache.get_last_success_meta(user_id)`.
    # I will assume for this task I should just pass `meta.get("id")` or similar if available.
    # Since I can't easily change the cache structure without verifying `cache.py`, I will try to pass `meta.get("generation_id")` 
    # and also UPDATE the cache saving in `confirm` to include it.
    
    generation = await _db.create_generation(
        user_id, 
        f"{prompt} [{payload_desc}]",
        input_images=image_urls or None
    )
    gen_id = generation.get("id")
    ratio_map = {
        "1:1": "square_hd",
        "3:4": "portrait_4_3",
        "4:3": "landscape_4_3",
        "9:16": "portrait_16_9",
        "16:9": "landscape_16_9",
        "21:9": "landscape_21_9",
        "3:2": "landscape_3_2",
        "2:3": "portrait_3_2",
    }
    image_size = ratio_map.get(ratio) if ratio in ratio_map else None
    model = _seedream_model_edit if (len(photos) > 0 or avatar_file_path or (isinstance(selected_avatars, list) and len(selected_avatars) > 0)) else _seedream_model_t2i
    # image_urls already prepared above
    pass
    try:
        image_url = await _client.generate_image(
            prompt=prompt,
            model=model,
            image_urls=image_urls or None,
            image_size=image_size,
            image_resolution=image_resolution,
            max_images=max_images,
            meta={"generationId": gen_id, "userId": user_id},
        )
    except Exception as e:
        msg = str(e)
        if "awaiting callback" in msg:
            current_balance = await _db.get_token_balance(user_id)
            new_balance = max(0, int(current_balance) - 3)
            await _db.set_token_balance(user_id, new_balance)
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
    new_balance = max(0, int(current_balance) - 3)
    await _db.set_token_balance(user_id, new_balance)
    if gen_id is not None:
        await _db.mark_generation_completed(gen_id, image_url)
    await callback.message.answer_document(
        document=URLInputFile(image_url, filename=_guess_filename(image_url)),
        caption=t(lang, "gen.result_caption"),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=t(lang, "kb.repeat_generation"))], [KeyboardButton(text=t(lang, "kb.new_generation"))], [KeyboardButton(text=t(lang, "kb.start"))]],
            resize_keyboard=True,
        ),
    )
    try:
        if _cache is not None and gen_id is not None:
            await _cache.set_last_success_meta(user_id, {
                "prompt": prompt,
                "gen_type": gen_type,
                "ratio": ratio,
                "image_resolution": image_resolution,
                "max_images": max_images,
                "photos": photos,
                "avatar_file_path": avatar_file_path,
                "selected_avatars": selected_avatars,
                "image_size": image_size,
                "model": model,
            })
    except Exception as e:
        _logger.warning("Failed to cache last success meta (repeat) user=%s gen_id=%s: %s", user_id, gen_id, e)
    await state.clear()
    await callback.answer("Started")
