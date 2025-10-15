import os
import json
from dataclasses import dataclass, field
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
    # Tribute payments
    tribute_api_key: Optional[str] = None
    tribute_product_map: dict[int, str] = field(default_factory=dict)  # tokens -> product_id (string or numeric)
    request_timeout_seconds: int = 60
    # Webhook/Server settings
    webhook_url: Optional[str] = None
    webhook_path: str = "/webhook"
    webhook_secret_token: Optional[str] = None


def load_settings() -> Settings:
    # Load from .env if present
    load_dotenv(override=False)

    bot_token = os.getenv("BOT_TOKEN", "")
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_KEY", "")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    nanobanana_api_base = os.getenv("NANOBANANA_API_BASE", "https://kie.ai/nano-banana")
    nanobanana_api_key = os.getenv("NANOBANANA_API_KEY")
    # Tribute payments
    tribute_api_key = os.getenv("TRIBUTE_API_KEY")
    tribute_product_map_raw = os.getenv("TRIBUTE_PRODUCT_MAP", "{}")
    try:
        parsed = json.loads(tribute_product_map_raw)
        tribute_product_map: dict[int, str] = {}
        for k, v in (parsed or {}).items():
            # tokens must be int-like
            try:
                tokens = int(str(k))
            except Exception:
                continue
            # product_id can be string slug or numeric; store as string
            pid = str(v).strip()
            if pid:
                tribute_product_map[tokens] = pid
    except Exception:
        tribute_product_map = {}
    request_timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
    # Webhook
    webhook_url = os.getenv("WEBHOOK_URL")
    webhook_path = os.getenv("WEBHOOK_PATH", "/webhook")
    webhook_secret_token = os.getenv("WEBHOOK_SECRET_TOKEN")

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
        tribute_api_key=tribute_api_key,
        tribute_product_map=tribute_product_map,
        request_timeout_seconds=request_timeout_seconds,
        webhook_url=webhook_url,
        webhook_path=webhook_path,
        webhook_secret_token=webhook_secret_token,
    )