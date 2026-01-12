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

from ..database import Database
from ..utils.i18n import t, normalize_lang
import io

router = Router(name="avatars")

_db: Database | None = None


def setup(database: Database) -> None:
    global _db
    _db = database


class AvatarStates(StatesGroup):
    waiting_photo = State()
    waiting_name = State()


def _avatars_list_keyboard(rows: list[dict], lang: str | None = None) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    # List existing avatars with delete button
    for r in rows:
        aid = r.get("id")
        name = r.get("display_name") or "—"
        # 🗑️ {name} -> callback: avatar:del:{id}
        kb.append([InlineKeyboardButton(text=f"🗑️ {name}", callback_data=f"avatar:del:{aid}")])
    
    # Add button
    kb.append([InlineKeyboardButton(text=t(lang, "avatars.add"), callback_data="avatar:add")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.message(Command("avatars"))
async def avatars_command(message: Message, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(message.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or message.from_user.language_code)
    
    items = await _db.list_avatars(message.from_user.id)
    if not items:
        # Show "Empty" message with "Add" button
        await message.answer(
            t(lang, "avatars.empty"),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=t(lang, "avatars.add"), callback_data="avatar:add")]]
            ),
        )
        return
    
    # Show list
    lines = [t(lang, "avatars.title"), t(lang, "avatars.delete_hint")]
    for r in items:
        lines.append(f"• {r.get('display_name')}")
    
    await message.answer("\n".join(lines), reply_markup=_avatars_list_keyboard(items, lang))


@router.callback_query(F.data == "avatar:add")
async def avatar_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    assert _db is not None
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    
    await state.clear()
    await state.set_state(AvatarStates.waiting_photo)
    await state.update_data(lang=lang)
    
    await callback.message.answer(t(lang, "avatars.upload_photo"))
    await callback.answer()


@router.message(StateFilter(AvatarStates.waiting_photo), F.photo)
async def avatar_receive_photo(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1]
    st = await state.get_data()
    lang = st.get("lang")
    
    # Download photo to memory
    f = await message.bot.get_file(photo.file_id)
    file_bytes = io.BytesIO()
    await message.bot.download_file(f.file_path, file_bytes)
    file_bytes.seek(0)
    
    await state.update_data(file_bytes=file_bytes.read().hex()) # Store as hex string to be json serializable? Or just keep in memory for short time?
    # Keeping bytes in FSM might be heavy if using Redis, but MemoryStorage is default.
    # Safe way: store file_id temporarily and download at the end? 
    # Actually, let's keep it simple: store file_id and download when saving to DB? 
    # But `upload_avatar` needs bytes.
    # Let's re-download at the end to be safe with storage limits, or just pass file_id to next step.
    # wait, message.bot.download_file writes to stream.
    
    await state.update_data(photo_file_id=photo.file_id)
    await state.set_state(AvatarStates.waiting_name)
    await message.answer(t(lang, "avatars.enter_name"))


@router.message(StateFilter(AvatarStates.waiting_name))
async def avatar_receive_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    st = await state.get_data()
    lang = st.get("lang")
    
    if not name:
        await message.answer(t(lang, "avatars.enter_name"))
        return
    
    if len(name) > 30:
        await message.answer("Name too long (max 30 chars). Try again.")
        return

    photo_file_id = st.get("photo_file_id")
    if not photo_file_id:
        await state.clear()
        await message.answer("Error: photo lost. Start over.")
        return

    assert _db is not None
    
    # Download file content
    try:
        f = await message.bot.get_file(photo_file_id)
        b = io.BytesIO()
        await message.bot.download_file(f.file_path, b)
        content = b.getvalue()
        
        # Upload
        await _db.upload_avatar(message.from_user.id, content, name)
        
        await message.answer(t(lang, "avatars.saved", name=name))
        await state.clear()
        
        # Show list again
        await avatars_command(message, state)
    except Exception as e:
        await message.answer(f"Error saving avatar: {e}")
        await state.clear()


@router.callback_query(F.data.startswith("avatar:del:"))
async def avatar_delete(callback: CallbackQuery) -> None:
    aid = callback.data.split(":", 2)[2]
    assert _db is not None
    
    user = await _db.get_user(callback.from_user.id) or {}
    lang = normalize_lang(user.get("language_code") or callback.from_user.language_code)
    
    success = await _db.delete_avatar(aid, callback.from_user.id)
    if success:
        await callback.answer(t(lang, "avatars.deleted"))
        # Refresh list
        items = await _db.list_avatars(callback.from_user.id)
        if not items:
             await callback.message.edit_text(
                t(lang, "avatars.empty"),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text=t(lang, "avatars.add"), callback_data="avatar:add")]]
                ),
            )
        else:
            lines = [t(lang, "avatars.title"), t(lang, "avatars.delete_hint")]
            for r in items:
                lines.append(f"• {r.get('display_name')}")
            await callback.message.edit_text("\n".join(lines), reply_markup=_avatars_list_keyboard(items, lang))
    else:
        await callback.answer("Error or not found", show_alert=True)


@router.message((F.text == t("ru", "avatars.btn_label")) | (F.text == t("en", "avatars.btn_label")))
@router.message(F.text.regexp(r"(?i)^\s.*\b(avatar|аватар).*\b"))
async def avatars_btn_handler(message: Message, state: FSMContext) -> None:
    await avatars_command(message, state)
