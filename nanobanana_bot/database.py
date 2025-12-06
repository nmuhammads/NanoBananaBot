from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timezone

from supabase import Client, create_client
from uuid import uuid4
import mimetypes
import os


class Database:
    def __init__(self, supabase_url: str, supabase_key: str):
        self.client: Client = create_client(supabase_url, supabase_key)

    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        language_code: Optional[str],
    ) -> Dict[str, Any]:
        # Existing user by primary key user_id
        existing = (
            self.client.table("users")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]

        created = (
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
        res = self.client.table("users").select("balance").eq("user_id", user_id).limit(1).execute()
        if res.data:
            return int(res.data[0].get("balance", 0))
        return 0

    async def set_token_balance(self, user_id: int, balance: int) -> None:
        # upsert by user_id
        self.client.table("users").upsert({"user_id": user_id, "balance": int(balance)}).execute()

    async def set_language_code(self, user_id: int, language_code: str) -> None:
        # update language for existing user
        self.client.table("users").update({"language_code": language_code}).eq("user_id", user_id).execute()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table("users").select("*").eq("user_id", user_id).limit(1).execute()
        )
        rows = getattr(res, "data", []) or []
        return rows[0] if rows else None

    async def set_ref(self, user_id: int, ref: str) -> None:
        self.client.table("users").update({"ref": str(ref)}).eq("user_id", int(user_id)).execute()

    async def upsert_user_ref(self, user_id: int, ref: str) -> None:
        self.client.table("users").upsert({"user_id": int(user_id), "ref": str(ref)}).execute()

    async def create_generation(
        self,
        user_id: int,
        prompt: str,
        parent_id: Optional[int] = None,
        input_images: Optional[List[str]] = None,
        model: str = "seedream4",
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

        created = self.client.table("generations").insert(data).execute()
        return created.data[0]

    async def mark_generation_completed(self, generation_id: int, media_url: str) -> None:
        completed_at = datetime.now(timezone.utc).isoformat()
        self.client.table("generations").update(
            {"status": "completed", "image_url": media_url, "completed_at": completed_at}
        ).eq("id", generation_id).execute()

    async def mark_generation_failed(self, generation_id: int, error_message: str) -> None:
        completed_at = datetime.now(timezone.utc).isoformat()
        self.client.table("generations").update(
            {"status": "failed", "error_message": error_message, "completed_at": completed_at}
        ).eq("id", generation_id).execute()

    async def update_generation_input_images(self, generation_id: int, input_images: List[str]) -> None:
        self.client.table("generations").update(
            {"input_images": input_images}
        ).eq("id", generation_id).execute()

    # === Avatars & Storage (photo_reference bucket) ===
    async def list_avatars(self, user_id: int) -> List[Dict[str, Any]]:
        res = (
            self.client.table("avatars")
            .select("id, user_id, display_name, file_path, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return getattr(res, "data", []) or []

    async def upload_avatar(self, user_id: int, file_bytes: bytes, display_name: str, content_type: Optional[str] = None) -> Dict[str, Any]:
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
        bucket.upload(path, file_bytes, {"contentType": content_type or "image/jpeg"})
        # Record in avatars table
        created = (
            self.client.table("avatars")
            .insert({
                "user_id": int(user_id),
                "file_path": path,
                "display_name": display_name.strip(),
            })
            .execute()
        )
        return created.data[0]

    async def delete_avatar(self, avatar_id: int) -> bool:
        # Fetch record to know file_path and user_id
        res = self.client.table("avatars").select("id, user_id, file_path").eq("id", int(avatar_id)).limit(1).execute()
        rows = getattr(res, "data", []) or []
        if not rows:
            return False
        rec = rows[0]
        file_path = rec.get("file_path")
        # Remove storage file first (ignore missing)
        try:
            self.client.storage.from_("photo_reference").remove([file_path])
        except Exception:
            pass
        # Delete DB record
        self.client.table("avatars").delete().eq("id", int(avatar_id)).execute()
        return True

    async def get_avatar(self, avatar_id: int) -> Optional[Dict[str, Any]]:
        res = self.client.table("avatars").select("id, user_id, display_name, file_path").eq("id", int(avatar_id)).limit(1).execute()
        rows = getattr(res, "data", []) or []
        return rows[0] if rows else None

    async def create_signed_url(self, file_path: str, expires_in: int = 300) -> str:
        # Create a temporary signed URL for private bucket access
        signed = self.client.storage.from_("photo_reference").create_signed_url(file_path, expires_in)
        # Supabase Python client returns dict with signedURL or fullURL depending on version
        if isinstance(signed, dict):
            return signed.get("signedURL") or signed.get("signed_url") or signed.get("fullURL") or signed.get("publicURL") or ""
        return str(signed)

    async def download_avatar_bytes(self, file_path: str) -> bytes:
        # Direct download via service_role; bucket is private
        data = self.client.storage.from_("photo_reference").download(file_path)
        # supabase-py returns bytes
        return data if isinstance(data, (bytes, bytearray)) else bytes(data)
