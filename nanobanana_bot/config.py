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
    seedream_api_base: str
    seedream_api_key: Optional[str] = None
    # Seedream model names (configurable)
    seedream_model_t2i: str = "bytedance/seedream-v4-text-to-image"
    seedream_model_edit: str = "bytedance/seedream-v4-edit"
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
    # Use official KIE API base for job endpoints by default
    seedream_api_base = os.getenv("SEEDREAM_API_BASE", "https://api.kie.ai/api/v1")
    seedream_api_key = os.getenv("SEEDREAM_API_KEY")
    # Seedream model names
    seedream_model_t2i = os.getenv("SEEDREAM_MODEL_T2I", "bytedance/seedream-v4-text-to-image")
    seedream_model_edit = os.getenv("SEEDREAM_MODEL_EDIT", "bytedance/seedream-v4-edit")
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
        # Fallback parser for non-JSON inputs like {"50":lJp}
        tribute_product_map = {}
        try:
            import re
            # Find pairs like "50":lJp or 50:plJp (with optional quotes)
            for m in re.finditer(r'"?(\d+)"?\s*:\s*"?([^"\s,}]+)"?', tribute_product_map_raw):
                try:
                    tokens = int(m.group(1))
                except Exception:
                    continue
                pid = m.group(2).strip()
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
        seedream_api_base=seedream_api_base,
        seedream_api_key=seedream_api_key,
        seedream_model_t2i=seedream_model_t2i,
        seedream_model_edit=seedream_model_edit,
        tribute_api_key=tribute_api_key,
        tribute_product_map=tribute_product_map,
        request_timeout_seconds=request_timeout_seconds,
        webhook_url=webhook_url,
        webhook_path=webhook_path,
        webhook_secret_token=webhook_secret_token,
    )