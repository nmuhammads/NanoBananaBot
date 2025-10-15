from aiogram import Router, F, html
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from ..utils.nanobanana import NanoBananaClient
from ..database import Database
from ..utils.i18n import t, normalize_lang
import logging


router = Router(name="generate")

_client: NanoBananaClient | None = None
_db: Database | None = None
_logger = logging.getLogger("nanobanana.generate")


def setup(client: NanoBananaClient, database: Database) -> None:
    global _client, _db
    _client = client
    _db = database

class GenerateStates(StatesGroup):
    choosing_type = State()
    waiting_prompt = State()
    waiting_photo_count = State()
    waiting_photos = State()
    choosing_ratio = State()
    confirming = State()


def type_keyboard(lang: str | None = None) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=t(lang, "gen.type.text"), callback_data="gen_type:text")],
        [InlineKeyboardButton(text=t(lang, "gen.type.text_photo"), callback_data="gen_type:text_photo")],
        [InlineKeyboardButton(text=t(lang, "gen.type.text_multi"), callback_data="gen_type:text_multi")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def ratio_keyboard() -> InlineKeyboardMarkup:
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
    rows = []
    row: list[InlineKeyboardButton] = []
    for i, label in enumerate(labels):
        row.append(InlineKeyboardButton(text=label, callback_data=f"ratio:{label}"))
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
    # Третий ряд: подтверждение
    rows.append([InlineKeyboardButton(text=t(lang, "gen.confirm_label"), callback_data="pc:confirm")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("generate"))
async def start_generate(message: Message, state: FSMContext) -> None:
    assert _client is not None and _db is not None

    # Проверка токенов в Supabase (баланс хранится только там)
    balance = await _db.get_token_balance(message.from_user.id)
    _logger.info("/generate start user=%s balance=%s", message.from_user.id, balance)
    if balance < 4:
        user = await _db.get_user(message.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
        await message.answer(t(lang, "gen.not_enough_tokens", balance=balance))
        _logger.warning("User %s has insufficient balance (need 4)", message.from_user.id)
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
    await state.set_state(GenerateStates.waiting_prompt)
    st = await state.get_data()
    lang = st.get("lang")
    await callback.message.edit_text(t(lang, "gen.enter_prompt"))
    await callback.answer()


@router.message(StateFilter(GenerateStates.waiting_prompt))
async def receive_prompt(message: Message, state: FSMContext) -> None:
    prompt = (message.text or "").strip()
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

    # Все фото получены — переходим к выбору соотношения сторон
    await state.set_state(GenerateStates.choosing_ratio)
    st = await state.get_data()
    lang = st.get("lang")
    await message.answer(t(lang, "gen.choose_ratio"), reply_markup=ratio_keyboard())


@router.message(StateFilter(GenerateStates.waiting_photos))
async def require_photo(message: Message, state: FSMContext) -> None:
    st = await state.get_data()
    photos = list(st.get("photos", []))
    photos_needed = int(st.get("photos_needed", 1))
    next_idx = min(len(photos) + 1, photos_needed)
    lang = st.get("lang")
    await message.answer(t(lang, "gen.require_photo", next=next_idx, total=photos_needed))


# Текстовый запуск генерации с нижней клавиатуры
@router.message((F.text == t("ru", "kb.generate")) | (F.text == t("en", "kb.generate")))
async def start_generate_text(message: Message, state: FSMContext) -> None:
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
        f"{t(lang, 'gen.summary.prompt', prompt=html.bold(prompt))}\n"
        f"{t(lang, 'gen.summary.ratio', ratio=ratio)}\n"
    )
    if gen_type in {"text_photo", "text_multi"}:
        summary += f"• Фото: {len(photos)} из {photos_needed}"

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

    # Проверка токенов перед запуском (Supabase)
    balance = await _db.get_token_balance(user_id)
    if balance < 4:
        lang = st.get("lang")
        await callback.message.edit_text(t(lang, "gen.not_enough_tokens", balance=balance))
        await state.clear()
        await callback.answer()
        _logger.warning("User %s insufficient balance at confirm (need 4)", user_id)
        return

    # Трекинг генерации в Supabase
    payload_desc = f"type={gen_type}; ratio={ratio}; photos={len(photos)}"
    generation = await _db.create_generation(user_id, f"{prompt} [{payload_desc}]")
    gen_id = generation.get("id")
    _logger.info("Generation created id=%s user=%s type=%s ratio=%s photos=%s", gen_id, user_id, gen_type, ratio, len(photos))

    # Подготовка параметров KIE API
    ratio_map = {
        "1:1": "1:1",
        "3:4": "3:4",
        "4:3": "4:3",
        "9:16": "9:16",
        "16:9": "16:9",
    }
    image_size = ratio_map.get(ratio, "1:1")
    # Выбор модели: если есть фото — edit, иначе text-only
    model = "google/nano-banana-edit" if len(photos) > 0 else "google/nano-banana"

    # Конвертация Telegram photo file_id → доступный URL (для edit-модели)
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

    try:
        _logger.info("Calling KIE API for user=%s gen_id=%s model=%s size=%s images=%s", user_id, gen_id, model, image_size, len(image_urls))
        image_url = await _client.generate_image(
            prompt=prompt,
            model=model,
            image_urls=image_urls or None,
            image_size=image_size,
            output_format="png",
            meta={"generationId": gen_id, "userId": user_id},
        )
    except Exception as e:
        msg = str(e)
        # Особый случай: провайдер принял задачу и пришлёт результат через callback
        if "awaiting callback" in msg:
            _logger.info("Async generation accepted: user=%s gen_id=%s", user_id, gen_id)
            # Списание 4 токенов сразу после принятия задачи
            current_balance = await _db.get_token_balance(user_id)
            new_balance = max(0, int(current_balance) - 4)
            await _db.set_token_balance(user_id, new_balance)
            _logger.info("Debited 4 tokens (async): user=%s balance %s->%s", user_id, current_balance, new_balance)
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

    # Списание 4 токенов и сохранение в Supabase (синхронный случай)
    current_balance = await _db.get_token_balance(user_id)
    new_balance = max(0, int(current_balance) - 4)
    await _db.set_token_balance(user_id, new_balance)
    _logger.info("Debited 4 tokens (sync): user=%s balance %s->%s", user_id, current_balance, new_balance)

    if gen_id is not None:
        await _db.mark_generation_completed(gen_id, image_url)

    lang = st.get("lang")
    await callback.message.edit_caption(
        caption=t(lang, "gen.done_text", balance=new_balance, ratio=ratio),
    ) if callback.message.photo else await callback.message.edit_text(
        t(lang, "gen.done_text", balance=new_balance, ratio=ratio)
    )
    # Отправим изображение отдельным сообщением
    await callback.message.answer_photo(photo=image_url, caption=t(lang, "gen.result_caption"))
    await state.clear()
    _logger.info("Generation completed: user=%s gen_id=%s image_url=%s", user_id, gen_id, image_url)
    await callback.answer("Started")