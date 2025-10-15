import logging
from typing import Any, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery


class SimpleLoggingMiddleware(BaseMiddleware):
    def __init__(
        self,
        logger: logging.Logger | None = None,
        truncate_len: int = 120,
        log_full_event: bool = False,
    ) -> None:
        super().__init__()
        self.logger = logger or logging.getLogger("nanobanana.middleware")
        self.truncate_len = int(truncate_len)
        self.log_full_event = bool(log_full_event)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            if isinstance(event, Message):
                user_id = event.from_user.id if event.from_user else None
                chat_id = event.chat.id if event.chat else None
                text = (event.text or event.caption or "")
                text_snippet = text[: self.truncate_len]
                self.logger.info(
                    "Message: user=%s chat=%s id=%s text=%r",
                    user_id,
                    chat_id,
                    getattr(event, "message_id", None),
                    text_snippet,
                )
            elif isinstance(event, CallbackQuery):
                user_id = event.from_user.id if event.from_user else None
                msg_id = event.message.message_id if event.message else None
                data_snippet = (event.data or "")[: self.truncate_len]
                self.logger.info(
                    "CallbackQuery: user=%s msg_id=%s data=%r",
                    user_id,
                    msg_id,
                    data_snippet,
                )
            else:
                # For other event types, log only the class name to avoid verbosity
                self.logger.info("Event: %s", event.__class__.__name__)

            # Full event dump only at DEBUG level and when explicitly enabled
            if self.log_full_event and self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("Full event: %s", event)
        except Exception:
            # Never let logging break the flow
            self.logger.debug("Failed to log event summary", exc_info=True)

        return await handler(event, data)