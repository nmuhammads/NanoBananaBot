from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
import logging

router = Router(name="fallback")
_logger = logging.getLogger("nanobanana.fallback")

# Debug handler for unhandled messages
@router.message(StateFilter("*"))
async def catch_all_debug(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    st = await state.get_state()
    _logger.info("DEBUG: Unhandled message text='%s' state='%s'", text, st)
