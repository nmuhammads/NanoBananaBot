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
from ..cache import Cache


router = Router(name="generate")

_client: NanoBananaClient | None = None
_db: Database | None = None
_cache: Cache | None = None


def setup(client: NanoBananaClient, database: Database, cache: Cache) -> None:
    global _client, _db, _cache
    _client = client
    _db = database
    _cache = cache

class GenerateStates(StatesGroup):
    choosing_type = State()
    waiting_prompt = State()
    waiting_photo_count = State()
    waiting_photos = State()
    choosing_ratio = State()
    confirming = State()


def type_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="По тексту", callback_data="gen_type:text")],
        [InlineKeyboardButton(text="По текст + фото", callback_data="gen_type:text_photo")],
        [InlineKeyboardButton(text="По текст + несколько фото", callback_data="gen_type:text_multi")],
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


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm:ok")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="confirm:cancel")],
        ]
    )


@router.message(Command("generate"))
async def start_generate(message: Message, state: FSMContext) -> None:
    assert _client is not None and _db is not None and _cache is not None

    # Token check (1 токен на генерацию)
    balance = await _cache.get_balance(message.from_user.id)
    if balance <= 0:
        await message.answer("Недостаточно токенов. Пополните баланс или обратитесь в поддержку.")
        return

    await state.clear()
    await state.set_state(GenerateStates.choosing_type)
    await state.update_data(user_id=message.from_user.id)
    await message.answer(
        "Выберите способ генерации:",
        reply_markup=type_keyboard(),
    )


@router.callback_query(StateFilter(GenerateStates.choosing_type))
async def choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if not data.startswith("gen_type:"):
        await callback.answer()
        return
    gen_type = data.split(":", 1)[1]
    await state.update_data(gen_type=gen_type)
    await state.set_state(GenerateStates.waiting_prompt)
    await callback.message.edit_text(
        "Введите текстовый промпт для генерации:"
    )
    await callback.answer()


@router.message(StateFilter(GenerateStates.waiting_prompt))
async def receive_prompt(message: Message, state: FSMContext) -> None:
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Пожалуйста, отправьте текстовый промпт.")
        return
    await state.update_data(prompt=prompt)

    data = await state.get_data()
    gen_type = data.get("gen_type")
    if gen_type == "text":
        await state.set_state(GenerateStates.choosing_ratio)
        await message.answer("Выберите соотношение сторон:", reply_markup=ratio_keyboard())
        return
    elif gen_type == "text_photo":
        await state.update_data(photos_needed=1, photos=[])
        await state.set_state(GenerateStates.waiting_photos)
        await message.answer("Загрузите фото, которое будет использовано вместе с текстом.")
        return
    elif gen_type == "text_multi":
        await state.set_state(GenerateStates.waiting_photo_count)
        await message.answer("Сколько фото использовать? Введите число от 1 до 10.")
        return
    else:
        await message.answer("Неизвестный тип генерации. Начните заново: /generate")
        await state.clear()


@router.message(StateFilter(GenerateStates.waiting_photo_count))
async def receive_photo_count(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        count = int(text)
    except ValueError:
        await message.answer("Введите число от 1 до 10.")
        return
    if count < 1 or count > 10:
        await message.answer("Число должно быть от 1 до 10.")
        return

    await state.update_data(photos_needed=count, photos=[])
    await state.set_state(GenerateStates.waiting_photos)
    await message.answer(f"Загрузите {count} фото по очереди. Пришлите первое фото.")


@router.message(StateFilter(GenerateStates.waiting_photos), F.photo)
async def receive_photo(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = list(data.get("photos", []))
    photos_needed = int(data.get("photos_needed", 1))

    photos.append(photo_id)
    await state.update_data(photos=photos)

    if len(photos) < photos_needed:
        await message.answer(f"Фото {len(photos)} из {photos_needed} получено. Пришлите следующее фото.")
        return

    # Все фото получены — переходим к выбору соотношения сторон
    await state.set_state(GenerateStates.choosing_ratio)
    await message.answer("Выберите соотношение сторон:", reply_markup=ratio_keyboard())


@router.message(StateFilter(GenerateStates.waiting_photos))
async def require_photo(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте фото.")


@router.callback_query(StateFilter(GenerateStates.choosing_ratio))
async def choose_ratio(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if not data.startswith("ratio:"):
        await callback.answer()
        return
    ratio = data.split(":", 1)[1]
    await state.update_data(ratio=ratio)

    st = await state.get_data()
    gen_type = st.get("gen_type")
    prompt = st.get("prompt")
    photos = st.get("photos", [])
    photos_needed = st.get("photos_needed")

    summary_lines = [
        "Проверьте данные перед генерацией:\n",
        f"Тип: {gen_type}",
        f"Промпт: {html.bold(prompt)}",
        f"Соотношение сторон: {ratio}",
    ]
    if gen_type in {"text_photo", "text_multi"}:
        summary_lines.append(f"Фото: {len(photos)} из {photos_needed}")

    await state.set_state(GenerateStates.confirming)
    await callback.message.edit_text("\n".join(summary_lines), reply_markup=confirm_keyboard())
    await callback.answer()


@router.callback_query(StateFilter(GenerateStates.confirming))
async def confirm(callback: CallbackQuery, state: FSMContext) -> None:
    choice = (callback.data or "")
    if choice == "confirm:cancel":
        await state.clear()
        await callback.message.edit_text("Генерация отменена.")
        await callback.answer("Отменено")
        return
    if choice != "confirm:ok":
        await callback.answer()
        return

    assert _client is not None and _db is not None and _cache is not None

    st = await state.get_data()
    user_id = int(st.get("user_id"))
    prompt = st.get("prompt")
    gen_type = st.get("gen_type")
    ratio = st.get("ratio", "auto")
    photos = st.get("photos", [])

    # Проверка токенов перед запуском
    balance = await _cache.get_balance(user_id)
    if balance <= 0:
        await callback.message.edit_text("Недостаточно токенов. Пополните баланс или обратитесь в поддержку.")
        await state.clear()
        await callback.answer()
        return

    # Трекинг генерации в Supabase
    payload_desc = f"type={gen_type}; ratio={ratio}; photos={len(photos)}"
    generation = await _db.create_generation(user_id, f"{prompt} [{payload_desc}]")
    gen_id = generation.get("id")

    try:
        # В текущей версии реализована генерация по тексту.
        # Режимы text_photo / text_multi будут подключены позже через API редактирования.
        image_url = await _client.generate_image(prompt)
    except Exception as e:
        if gen_id is not None:
            await _db.mark_generation_failed(gen_id, str(e))
        await callback.message.edit_text(f"Ошибка генерации: {e}")
        await state.clear()
        await callback.answer()
        return

    # Списание токена и сохранение
    new_balance = await _cache.increment_balance(user_id, -1)
    await _db.set_token_balance(user_id, new_balance)

    if gen_id is not None:
        await _db.mark_generation_completed(gen_id, image_url)

    await callback.message.edit_caption(
        caption=f"Готово! Остаток токенов: {new_balance}\nСоотношение: {ratio}",
    ) if callback.message.photo else await callback.message.edit_text(
        f"Готово! Остаток токенов: {new_balance}\nСоотношение: {ratio}"
    )
    # Отправим изображение отдельным сообщением
    await callback.message.answer_photo(photo=image_url, caption=f"Результат генерации")
    await state.clear()
    await callback.answer("Запущено")