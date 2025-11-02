from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import logging
import httpx

from ..database import Database
from ..utils.i18n import t, normalize_lang


router = Router(name="avatars")
_db: Database | None = None
_logger = logging.getLogger("seedream.avatars")


class AvatarManagement(StatesGroup):
    adding_photo = State()
    adding_name = State()


def setup(database: Database) -> None:
    global _db
    _db = database


def _avatars_list_keyboard(rows: list[dict], lang: str | None = None) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    for r in rows:
        aid = r.get("id")
        name = r.get("display_name") or "—"
        kb.append([InlineKeyboardButton(text=f"🗑️ {name}", callback_data=f"avatar:del:{aid}")])
    kb.append([InlineKeyboardButton(text=t(lang, "avatars.add"), callback_data="avatar:add")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def _delete_confirm_keyboard(aid: int, lang: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "avatars.btn_delete"), callback_data=f"avatar:del_confirm:{aid}")],
            [InlineKeyboardButton(text=t(lang, "gen.confirm.cancel"), callback_data="avatar:del_cancel")],
        ]
    )


@router.message(Command("avatars"))
async def avatars_command(message: Message, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    items = await _db.list_avatars(message.from_user.id)
    if not items:
        await message.answer(
            t(lang, "avatars.empty"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t(lang, "avatars.add"), callback_data="avatar:add")]]
            ),
        )
        return
    # Show list and delete buttons
    lines = [t(lang, "avatars.title"), t(lang, "avatars.delete_hint")]
    for r in items:
        lines.append(f"• {r.get('display_name')}")
    await message.answer("\n".join(lines), reply_markup=_avatars_list_keyboard(items, lang))


# Запуск раздела по кнопке с нижней клавиатуры
@router.message((F.text == t("ru", "kb.avatars")) | (F.text == t("en", "kb.avatars")))
async def avatars_text(message: Message, state: FSMContext) -> None:
    await avatars_command(message, state)

# Fallback по тексту, если эмодзи/вариации отличаются
@router.message(F.text.regexp(r"(?i)^\s*\/?\s*(Мои\s+аватары|My\s+Avatars).*$"))
async def avatars_text_fallback(message: Message, state: FSMContext) -> None:
    await avatars_command(message, state)


@router.callback_query(F.data == "avatar:add")
async def add_avatar_cb(callback: CallbackQuery, state: FSMContext) -> None:
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    await state.set_state(AvatarManagement.adding_photo)
    await callback.message.answer(t(lang, "avatars.prompt_photo"))
    await callback.answer()


@router.message(StateFilter(AvatarManagement.adding_photo), F.photo)
async def receive_avatar_photo(message: Message, state: FSMContext) -> None:
    # Download file bytes from Telegram
    try:
        f = await message.bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{f.file_path}"
        async with httpx.AsyncClient(timeout=20.0) as hc:
            resp = await hc.get(file_url)
            resp.raise_for_status()
            content = resp.content
            # Guess content type from extension
            ct = "image/jpeg"
            if f.file_path.lower().endswith(".png"):
                ct = "image/png"
            elif f.file_path.lower().endswith(".webp"):
                ct = "image/webp"
        await state.update_data(pending_avatar_bytes=content, pending_avatar_ct=ct)
    except Exception as e:
        _logger.warning("Failed to download telegram photo for avatar: %s", e)
        user = await _db.get_user(message.from_user.id) or {}
        lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
        await message.answer(t(lang, "avatars.error_upload"))
        await state.clear()
        return

    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    await state.set_state(AvatarManagement.adding_name)
    await message.answer(
        t(lang, "avatars.prompt_name"),
        reply_markup=ForceReply(input_field_placeholder=t(lang, "avatars.ph_name"), selective=False),
    )
    # Кнопка отмены под полем ввода
    await message.answer(
        t(lang, "avatars.add.cancel_hint"),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t(lang, "gen.confirm.cancel"), callback_data="avatar:add_cancel")]]
        ),
    )


@router.message(StateFilter(AvatarManagement.adding_name))
async def receive_avatar_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    if not name:
        await message.answer(t(lang, "avatars.name_empty"))
        return
    st = await state.get_data()
    content = st.get("pending_avatar_bytes")
    ct = st.get("pending_avatar_ct")
    if not isinstance(content, (bytes, bytearray)):
        await message.answer(t(lang, "avatars.error_upload"))
        await state.clear()
        return
    try:
        rec = await _db.upload_avatar(message.from_user.id, content, name, ct)
        await message.answer(t(lang, "avatars.saved", name=rec.get("display_name")))
        await state.clear()
    except Exception as e:
        _logger.exception("Failed to save avatar: %s", e)
        await message.answer(t(lang, "avatars.error_upload"))
        await state.clear()


@router.callback_query(F.data.startswith("avatar:del:"))
async def delete_avatar_cb(callback: CallbackQuery, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    try:
        aid = int((callback.data or "").split(":")[-1])
    except Exception:
        await callback.answer()
        return
    # Найдём имя для подтверждения
    items = await _db.list_avatars(callback.from_user.id)
    name = None
    for r in items or []:
        try:
            if int(r.get("id")) == aid:
                name = r.get("display_name")
                break
        except Exception:
            continue
    display_name = name or "—"
    # Показать подтверждение удаления
    await callback.message.answer(
        t(lang, "avatars.confirm_delete", name=display_name),
        reply_markup=_delete_confirm_keyboard(aid, lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("avatar:del_confirm:"))
async def confirm_delete_avatar_cb(callback: CallbackQuery, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    try:
        aid = int((callback.data or "").split(":")[-1])
    except Exception:
        await callback.answer()
        return
    ok = await _db.delete_avatar(aid)
    if not ok:
        await callback.answer(t(lang, "avatars.error_delete"), show_alert=True)
        return
    # Обновим список
    await avatars_command(callback.message, state)
    await callback.answer(t(lang, "avatars.deleted"))


@router.callback_query(F.data == "avatar:del_cancel")
async def cancel_delete_avatar_cb(callback: CallbackQuery, state: FSMContext) -> None:
    # Просто перерисуем список
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    await avatars_command(callback.message, state)
    await callback.answer(t(lang, "gen.confirm.cancel"))


@router.callback_query(F.data == "avatar:add_cancel")
async def cancel_add_avatar_cb(callback: CallbackQuery, state: FSMContext) -> None:
    # Отменить добавление и вернуть список
    await state.clear()
    await avatars_command(callback.message, state)
    await callback.answer(t((await _db.get_user(callback.from_user.id) or {}).get("language_code") or callback.from_user.language_code, "gen.confirm.cancel"))