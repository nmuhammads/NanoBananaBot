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

    @property
    def _client(self) -> AsyncClient:
        client = self.client
        if client is None:
            raise RuntimeError("Supabase client is not initialized. Call Database.init() first.")
        return client

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
            self._client.table("users")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]

        created = await (
            self._client.table("users")
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
        res = await self._client.table("users").select("balance").eq("user_id", user_id).limit(1).execute()
        if res.data:
            return int(res.data[0].get("balance", 0))
        return 0

    async def set_token_balance(self, user_id: int, balance: int) -> None:
        # upsert by user_id
        await self._client.table("users").upsert({"user_id": user_id, "balance": int(balance)}).execute()

    async def set_language_code(self, user_id: int, language_code: str) -> None:
        # update language for existing user
        await self._client.table("users").update({"language_code": language_code}).eq("user_id", user_id).execute()

    async def set_ref(self, user_id: int, ref: str) -> None:
        await self._client.table("users").update({"ref": str(ref)}).eq("user_id", int(user_id)).execute()

    async def upsert_user_ref(self, user_id: int, ref: str) -> None:
        await self._client.table("users").upsert({"user_id": int(user_id), "ref": str(ref)}).execute()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        res = await (
            self._client.table("users").select("*").eq("user_id", user_id).limit(1).execute()
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

        created = await self._client.table("generations").insert(data).execute()
        return created.data[0]

    async def mark_generation_completed(self, generation_id: int, media_url: str) -> None:
        completed_at = datetime.now(timezone.utc).isoformat()
        await self._client.table("generations").update(
            {"status": "completed", "image_url": media_url, "completed_at": completed_at}
        ).eq("id", generation_id).execute()

    async def mark_generation_failed(self, generation_id: int, error_message: str) -> None:
        completed_at = datetime.now(timezone.utc).isoformat()
        await self._client.table("generations").update(
            {"status": "failed", "error_message": error_message, "completed_at": completed_at}
        ).eq("id", generation_id).execute()

    async def update_generation_input_images(self, generation_id: int, input_images: List[str]) -> None:
        await self._client.table("generations").update(
            {"input_images": input_images}
        ).eq("id", generation_id).execute()

    async def get_last_completed_generation(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает последнюю успешно завершённую генерацию пользователя."""
        res = await (
            self._client.table("generations")
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
        await self._client.table("bot_subscriptions").upsert(
            {"user_id": int(user_id), "bot_source": str(bot_source)},
            on_conflict="user_id,bot_source",
        ).execute()

    async def has_bot_subscription(self, user_id: int, bot_source: str) -> bool:
        res = await (
            self._client.table("bot_subscriptions")
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
            self._client.table("generations")
            .select("*")
            .eq("id", generation_id)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", []) or []
        return rows[0] if rows else None

    async def get_author_prompt(self, prompt_id: int) -> Optional[Dict[str, Any]]:
        res = await (
            self._client.table("author_prompts")
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
        # Determine reliable image MIME first so storage metadata is correct.
        resolved_content_type = self._resolve_image_content_type(file_bytes, content_type)
        # Determine extension from content type; default to .jpg
        ext = ".jpg"
        guessed = mimetypes.guess_extension(resolved_content_type)
        if guessed == ".jpe":
            guessed = ".jpg"
        if guessed:
            ext = guessed
        elif content_type:
            guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
            if isinstance(guessed, str) and guessed:
                ext = guessed
        # Path: {user_id}/{uuid}.ext
        path = f"{int(user_id)}/{uuid4().hex}{ext}"
        bucket = self._client.storage.from_("photo_reference")
        # Upload (private bucket). If file exists, let it fail
        await bucket.upload(path, file_bytes, {"content-type": resolved_content_type})
        # Record in avatars table
        created = await (
            self._client.table("avatars")
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

    @staticmethod
    def _resolve_image_content_type(file_bytes: bytes, content_type: Optional[str]) -> str:
        # Prefer explicit image content type, otherwise detect by magic bytes.
        raw = (content_type or "").split(";", 1)[0].strip().lower()
        if raw.startswith("image/"):
            return raw

        if file_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if file_bytes.startswith(b"GIF87a") or file_bytes.startswith(b"GIF89a"):
            return "image/gif"
        if file_bytes.startswith(b"RIFF") and file_bytes[8:12] == b"WEBP":
            return "image/webp"
        if file_bytes.startswith(b"BM"):
            return "image/bmp"

        return "image/jpeg"

    async def list_avatars(self, user_id: int) -> List[Dict[str, Any]]:
        res = await (
            self._client.table("avatars")
            .select("*")
            .eq("user_id", int(user_id))
            .order("created_at", desc=True)
            .execute()
        )
        return getattr(res, "data", []) or []

    async def delete_avatar(self, avatar_id: str, user_id: int) -> bool:
        # First get the avatar to find file path
        res = await (
            self._client.table("avatars")
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
        await self._client.table("avatars").delete().eq("id", avatar_id).execute()
        
        # Delete from storage
        if file_path:
            try:
                await self._client.storage.from_("photo_reference").remove([file_path])
            except Exception:
                # Log or ignore if already gone
                pass
        return True

    async def get_avatar(self, avatar_id: str) -> Optional[Dict[str, Any]]:
        res = await (
            self._client.table("avatars")
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
            signed = await self._client.storage.from_("photo_reference").create_signed_url(file_path, expires_in)
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
                self._client.table("app_config")
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
        await self._client.table("app_config").upsert(
            {"key": key, "value": value},
            on_conflict="key"
        ).execute()

    async def update_generation_provider(self, generation_id: int, provider: str) -> None:
        """Update api_provider field for generation."""
        await self._client.table("generations").update(
            {"api_provider": provider}
        ).eq("id", generation_id).execute()

    async def get_user_language(self, user_id: int) -> str:
        """Get user language code, defaults to 'ru'."""
        try:
            res = await self._client.table("users").select("language_code").eq("user_id", int(user_id)).limit(1).execute()
            rows = getattr(res, "data", []) or []
            if rows:
                return rows[0].get("language_code") or "ru"
        except Exception:
            pass
        return "ru"

    async def get_generation_user_id(self, generation_id: int) -> Optional[int]:
        """Get user_id from generation record."""
        try:
            res = await self._client.table("generations").select("user_id").eq("id", int(generation_id)).limit(1).execute()
            rows = getattr(res, "data", []) or []
            if rows:
                return rows[0].get("user_id")
        except Exception:
            pass
        return None
