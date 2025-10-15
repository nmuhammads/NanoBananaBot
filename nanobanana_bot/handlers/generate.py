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
    assert _client is not None and _db is not None

    # Проверка токенов в Supabase (баланс хранится только там)
    balance = await _db.get_token_balance(message.from_user.id)
    _logger.info("/generate start user=%s balance=%s", message.from_user.id, balance)
    if balance < 4:
        await message.answer(
            f"Недостаточно токенов: требуется 4 токена за генерацию. Ваш баланс: {balance}.\nПополнить баланс: /topup"
        )
        _logger.warning("User %s has insufficient balance (need 4)", message.from_user.id)
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
    _logger.info("User %s chose type=%s", callback.from_user.id, gen_type)
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
        _logger.warning("User %s sent empty prompt", message.from_user.id)
        return
    _logger.info("User %s provided prompt len=%s", message.from_user.id, len(prompt))
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
        _logger.info("User %s chose multi-photo mode", message.from_user.id)
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
        _logger.warning("User %s provided invalid photo count: %s", message.from_user.id, text)
        return
    if count < 1 or count > 10:
        await message.answer("Число должно быть от 1 до 10.")
        _logger.warning("User %s photo count out of range: %s", message.from_user.id, count)
        return

    await state.update_data(photos_needed=count, photos=[])
    await state.set_state(GenerateStates.waiting_photos)
    await message.answer(f"Загрузите {count} фото по очереди. Пришлите первое фото.")
    _logger.info("User %s expects photos=%s", message.from_user.id, count)


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
    _logger.info("User %s chose ratio=%s", callback.from_user.id, ratio)

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
        await callback.message.edit_text(
            f"Недостаточно токенов: требуется 4 токена за генерацию. Ваш баланс: {balance}.\nПополнить баланс: /topup"
        )
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
            await callback.message.edit_text(
                "Задача отправлена в генерацию. Результат придёт в этом чате чуть позже."
            )
            await state.clear()
            await callback.answer("Запущено")
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

    await callback.message.edit_caption(
        caption=f"Готово! Остаток токенов: {new_balance}\nСоотношение: {ratio}",
    ) if callback.message.photo else await callback.message.edit_text(
        f"Готово! Остаток токенов: {new_balance}\nСоотношение: {ratio}"
    )
    # Отправим изображение отдельным сообщением
    await callback.message.answer_photo(photo=image_url, caption=f"Результат генерации")
    await state.clear()
    _logger.info("Generation completed: user=%s gen_id=%s image_url=%s", user_id, gen_id, image_url)
    await callback.answer("Запущено")