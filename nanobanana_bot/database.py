from typing import Any, Dict, Optional
from datetime import datetime, timezone

from supabase import Client, create_client


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

    async def create_generation(self, user_id: int, prompt: str) -> Dict[str, Any]:
        created = (
            self.client.table("generations")
            .insert({"user_id": user_id, "prompt": prompt, "status": "pending"})
            .execute()
        )
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