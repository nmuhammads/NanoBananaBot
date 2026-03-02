import logging

import httpx
from aiogram import Bot


_logger = logging.getLogger("nanobanana.telegram_draft")


async def send_message_draft(bot: Bot, chat_id: int, draft_id: int, text: str) -> bool:
    """Send a real-time draft message (Bot API 9.5)."""
    if not text:
        return False

    try:
        chat_id_int = int(chat_id)
        draft_id_int = int(draft_id)
    except Exception:
        return False

    # sendMessageDraft is supported for private chats only; user IDs are positive ints.
    if chat_id_int <= 0 or draft_id_int == 0:
        return False

    payload = {
        "chat_id": chat_id_int,
        "draft_id": draft_id_int,
        "text": text,
    }
    url = f"https://api.telegram.org/bot{bot.token}/sendMessageDraft"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
        if response.status_code >= 400:
            _logger.debug(
                "sendMessageDraft failed: status=%s body=%s",
                response.status_code,
                response.text[:400],
            )
            return False
        data = response.json()
        ok = bool(data.get("ok"))
        if not ok:
            _logger.debug("sendMessageDraft not ok: %s", data)
        return ok
    except Exception:
        _logger.debug("sendMessageDraft request failed", exc_info=True)
        return False
