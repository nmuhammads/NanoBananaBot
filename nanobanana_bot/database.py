from typing import Any, Dict, Optional, List
from datetime import datetime, timezone
from uuid import uuid4
import mimetypes

from supabase import AsyncClient, acreate_client


class Database:
    def __init__(self, supabase_url: str, supabase_key: str):
        self._url = supabase_url
        self._key = supabase_key
        self.client: Optional[AsyncClient] = None

    async def init(self) -> None:
        """Initialize async Supabase client. Must be called once during app startup."""
        if self.client is None:
            self.client = await acreate_client(self._url, self._key)

    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        language_code: Optional[str],
    ) -> Dict[str, Any]:
        # Existing user by primary key user_id
        existing = await (
            self.client.table("users")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]

        created = await (
            self.client.table("users")
            .insert(
                {
                    "user_id": user_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "language_code": language_code,
                    # balance defaults to 0 per schema
                }
            )
            .execute()
        )
        return created.data[0]

    async def get_token_balance(self, user_id: int) -> int:
        res = await self.client.table("users").select("balance").eq("user_id", user_id).limit(1).execute()
        if res.data:
            return int(res.data[0].get("balance", 0))
        return 0

    async def set_token_balance(self, user_id: int, balance: int) -> None:
        # upsert by user_id
        await self.client.table("users").upsert({"user_id": user_id, "balance": int(balance)}).execute()

    async def set_language_code(self, user_id: int, language_code: str) -> None:
        # update language for existing user
        await self.client.table("users").update({"language_code": language_code}).eq("user_id", user_id).execute()

    async def set_ref(self, user_id: int, ref: str) -> None:
        await self.client.table("users").update({"ref": str(ref)}).eq("user_id", int(user_id)).execute()

    async def upsert_user_ref(self, user_id: int, ref: str) -> None:
        await self.client.table("users").upsert({"user_id": int(user_id), "ref": str(ref)}).execute()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        res = await (
            self.client.table("users").select("*").eq("user_id", user_id).limit(1).execute()
        )
        rows = getattr(res, "data", []) or []
        return rows[0] if rows else None

    async def create_generation(
        self,
        user_id: int,
        prompt: str,
        model: str,
        parent_id: Optional[int] = None,
        input_images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        data = {
            "user_id": user_id,
            "prompt": prompt,
            "status": "pending",
            "model": model,
        }
        if parent_id is not None:
            data["parent_id"] = parent_id
        if input_images is not None:
            data["input_images"] = input_images

        created = await self.client.table("generations").insert(data).execute()
        return created.data[0]

    async def mark_generation_completed(self, generation_id: int, media_url: str) -> None:
        completed_at = datetime.now(timezone.utc).isoformat()
        await self.client.table("generations").update(
            {"status": "completed", "image_url": media_url, "completed_at": completed_at}
        ).eq("id", generation_id).execute()

    async def mark_generation_failed(self, generation_id: int, error_message: str) -> None:
        completed_at = datetime.now(timezone.utc).isoformat()
        await self.client.table("generations").update(
            {"status": "failed", "error_message": error_message, "completed_at": completed_at}
        ).eq("id", generation_id).execute()

    async def update_generation_input_images(self, generation_id: int, input_images: List[str]) -> None:
        await self.client.table("generations").update(
            {"input_images": input_images}
        ).eq("id", generation_id).execute()

    async def get_last_completed_generation(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает последнюю успешно завершённую генерацию пользователя."""
        res = await (
            self.client.table("generations")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "completed")
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", []) or []
        return rows[0] if rows else None

    async def ensure_bot_subscription(self, user_id: int, bot_source: str) -> None:
        await self.client.table("bot_subscriptions").upsert(
            {"user_id": int(user_id), "bot_source": str(bot_source)},
            on_conflict="user_id,bot_source",
        ).execute()

    async def has_bot_subscription(self, user_id: int, bot_source: str) -> bool:
        res = await (
            self.client.table("bot_subscriptions")
            .select("user_id, bot_source")
            .eq("user_id", int(user_id))
            .eq("bot_source", str(bot_source))
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", []) or []
        return bool(rows)

    async def get_generation(self, generation_id: int) -> Optional[Dict[str, Any]]:
        res = await (
            self.client.table("generations")
            .select("*")
            .eq("id", generation_id)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", []) or []
        return rows[0] if rows else None

    async def get_author_prompt(self, prompt_id: int) -> Optional[Dict[str, Any]]:
        res = await (
            self.client.table("author_prompts")
            .select("*")
            .eq("id", prompt_id)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", []) or []
        return rows[0] if rows else None

    async def upload_avatar(
        self, user_id: int, file_bytes: bytes, display_name: str, content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        # Determine extension from content type; default to .jpg
        ext = ".jpg"
        if content_type:
            guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
            if isinstance(guessed, str) and guessed:
                ext = guessed
        # Path: {user_id}/{uuid}.ext
        path = f"{int(user_id)}/{uuid4().hex}{ext}"
        bucket = self.client.storage.from_("photo_reference")
        # Upload (private bucket). If file exists, let it fail
        await bucket.upload(path, file_bytes, {"content-type": content_type or "image/jpeg"})
        # Record in avatars table
        created = await (
            self.client.table("avatars")
            .insert(
                {
                    "user_id": int(user_id),
                    "file_path": path,
                    "display_name": display_name.strip(),
                }
            )
            .execute()
        )
        return created.data[0]

    async def list_avatars(self, user_id: int) -> List[Dict[str, Any]]:
        res = await (
            self.client.table("avatars")
            .select("*")
            .eq("user_id", int(user_id))
            .order("created_at", desc=True)
            .execute()
        )
        return getattr(res, "data", []) or []

    async def delete_avatar(self, avatar_id: str, user_id: int) -> bool:
        # First get the avatar to find file path
        res = await (
            self.client.table("avatars")
            .select("*")
            .eq("id", avatar_id)
            .eq("user_id", int(user_id))
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", []) or []
        if not rows:
            return False
        
        row = rows[0]
        file_path = row.get("file_path")
        
        # Delete from DB
        await self.client.table("avatars").delete().eq("id", avatar_id).execute()
        
        # Delete from storage
        if file_path:
            try:
                await self.client.storage.from_("photo_reference").remove([file_path])
            except Exception:
                # Log or ignore if already gone
                pass
        return True

    async def get_avatar(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        res = await (
            self.client.table("avatars")
            .select("*")
            .eq("id", avatar_id)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", []) or []
        return rows[0] if rows else None

    async def create_signed_url(self, file_path: str, expires_in: int = 300) -> str:
        # Create a temporary signed URL for private bucket access
        try:
            signed = await self.client.storage.from_("photo_reference").create_signed_url(file_path, expires_in)
            # Supabase Python client returns dict with signedURL or fullURL depending on version
            if isinstance(signed, dict):
                return signed.get("signedURL") or signed.get("signed_url") or signed.get("fullURL") or signed.get("publicURL") or ""
            return str(signed)
        except Exception:
            return ""

    async def get_app_config(self, key: str) -> Optional[str]:
        """Get config value from app_config table."""
        try:
            res = await (
                self.client.table("app_config")
                .select("value")
                .eq("key", key)
                .limit(1)
                .execute()
            )
            rows = getattr(res, "data", []) or []
            if rows:
                return rows[0].get("value")
        except Exception:
            pass
        return None

    async def set_app_config(self, key: str, value: str) -> None:
        """Set config value in app_config table."""
        await self.client.table("app_config").upsert(
            {"key": key, "value": value},
            on_conflict="key"
        ).execute()

    async def update_generation_provider(self, generation_id: int, provider: str) -> None:
        """Update api_provider field for generation."""
        await self.client.table("generations").update(
            {"api_provider": provider}
        ).eq("id", generation_id).execute()

    async def get_user_language(self, user_id: int) -> str:
        """Get user language code, defaults to 'ru'."""
        try:
            res = await self.client.table("users").select("language_code").eq("user_id", int(user_id)).limit(1).execute()
            rows = getattr(res, "data", []) or []
            if rows:
                return rows[0].get("language_code") or "ru"
        except Exception:
            pass
        return "ru"

    async def get_generation_user_id(self, generation_id: int) -> Optional[int]:
        """Get user_id from generation record."""
        try:
            res = await self.client.table("generations").select("user_id").eq("id", int(generation_id)).limit(1).execute()
            rows = getattr(res, "data", []) or []
            if rows:
                return rows[0].get("user_id")
        except Exception:
            pass
        return None
