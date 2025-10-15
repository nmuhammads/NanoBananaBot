import logging
from typing import Any, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class SimpleLoggingMiddleware(BaseMiddleware):
    def __init__(self, logger: logging.Logger | None = None) -> None:
        super().__init__()
        self.logger = logger or logging.getLogger("nanobanana.middleware")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        self.logger.info("Incoming event: %s", event)
        return await handler(event, data)