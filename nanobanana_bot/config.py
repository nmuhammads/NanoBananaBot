import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    bot_token: str
    supabase_url: str
    supabase_key: str
    redis_url: str
    nanobanana_api_base: str
    nanobanana_api_key: Optional[str] = None
    request_timeout_seconds: int = 60


def load_settings() -> Settings:
    # Load from .env if present
    load_dotenv(override=False)

    bot_token = os.getenv("BOT_TOKEN", "")
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    nanobanana_api_base = os.getenv("NANOBANANA_API_BASE", "https://kie.ai/nano-banana")
    nanobanana_api_key = os.getenv("NANOBANANA_API_KEY")
    request_timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required")

    return Settings(
        bot_token=bot_token,
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        redis_url=redis_url,
        nanobanana_api_base=nanobanana_api_base,
        nanobanana_api_key=nanobanana_api_key,
        request_timeout_seconds=request_timeout_seconds,
    )