"""
Generation Service - Сервис генерации с fallback логикой.
Управляет переключением между провайдерами (Kie.ai и Piapi).
"""

import logging
from typing import Optional, List, Dict, Any, Literal

from .nanobanana import NanoBananaClient
from .piapi import PiapiClient


ApiProvider = Literal["kie", "piapi"]


# Ошибки, при которых нужно переключиться на резервный провайдер
FALLBACK_ERROR_PATTERNS = [
    "503", "502", "500", "524",  # Service unavailable
    "401", "403", "access", "permission", "unauthorized",  # Auth errors (expired/invalid key)
    "429", "too many requests", "rate limit",  # Rate limiting
    "timeout", "econnrefused", "connection refused",  # Network errors
    "temporarily unavailable",
    "internal error",
    "internal server error",
    "ai studio api http error",
    "service unavailable",
]


class GenerationService:
    """
    Service that handles NanoBanana Pro generation with fallback between providers.
    
    Primary provider: Kie.ai
    Fallback provider: Piapi
    """

    def __init__(
        self,
        kie_client: NanoBananaClient,
        piapi_client: PiapiClient,
        db: Any,  # Database instance
    ):
        self.kie = kie_client
        self.piapi = piapi_client
        self.db = db
        self._logger = logging.getLogger("nanobanana.generation_service")

    async def get_primary_provider(self) -> ApiProvider:
        """Get current primary provider from database config."""
        try:
            value = await self.db.get_app_config("image_generation_primary_api")
            if value == "piapi":
                return "piapi"
        except Exception as e:
            self._logger.warning("Failed to get primary provider from config: %s", e)
        return "kie"

    async def set_primary_provider(self, provider: ApiProvider) -> None:
        """Set primary provider in database config."""
        try:
            await self.db.set_app_config("image_generation_primary_api", provider)
            self._logger.info("Switched primary provider to: %s", provider)
        except Exception as e:
            self._logger.warning("Failed to set primary provider: %s", e)

    def is_service_unavailable_error(self, error: Exception) -> bool:
        """
        Check if error indicates service unavailability (should trigger fallback).
        
        Does NOT trigger fallback for content policy errors (Gemini could not generate).
        """
        msg = str(error).lower()
        
        # Content policy errors should NOT trigger fallback
        if "gemini could not generate" in msg or "could not generate an image" in msg:
            return False
        if "sensitive" in msg or "e005" in msg:
            return False
        if "nsfw" in msg:
            return False
        
        # Check for service availability errors
        for pattern in FALLBACK_ERROR_PATTERNS:
            if pattern in msg:
                return True
        
        return False

    async def generate_pro(
        self,
        prompt: str,
        image_urls: Optional[List[str]] = None,
        aspect_ratio: Optional[str] = None,
        resolution: str = "2K",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate NanoBanana Pro image with fallback to secondary provider.
        
        Returns dict with keys:
            - task_id: str
            - provider: 'kie' | 'piapi'
            - awaiting_callback: bool (if True, result will come via webhook)
        
        Raises RuntimeError on both providers failing.
        """
        primary = await self.get_primary_provider()
        backup: ApiProvider = "piapi" if primary == "kie" else "kie"
        
        self._logger.info(
            "Starting NanoBanana Pro generation: primary=%s, backup=%s",
            primary, backup
        )

        # Helper to generate with specific provider
        async def generate_with(provider: ApiProvider) -> Dict[str, Any]:
            if provider == "piapi":
                task_id = await self.piapi.create_task(
                    prompt=prompt,
                    image_urls=image_urls,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    meta=meta,
                )
                return {
                    "task_id": task_id,
                    "provider": "piapi",
                    "awaiting_callback": True,
                }
            else:
                # Kie.ai via NanoBananaClient
                try:
                    result = await self.kie.generate_image(
                        prompt=prompt,
                        model="nano-banana-pro",
                        image_urls=image_urls,
                        image_size=aspect_ratio,
                        resolution=resolution,
                        meta=meta,
                    )
                    # If we got an image URL directly, return it
                    if result and not result.startswith("TIMEOUT"):
                        return {
                            "task_id": None,
                            "provider": "kie",
                            "awaiting_callback": False,
                            "image_url": result,
                        }
                except RuntimeError as e:
                    # Kie returns RuntimeError("awaiting callback") for async flow
                    if "awaiting callback" in str(e).lower():
                        return {
                            "task_id": None,
                            "provider": "kie",
                            "awaiting_callback": True,
                        }
                    raise
                
                return {
                    "task_id": None,
                    "provider": "kie",
                    "awaiting_callback": True,
                }

        # Try primary provider
        try:
            result = await generate_with(primary)
            self._logger.info("Generation started with primary provider: %s", primary)
            return result
            
        except Exception as error:
            # Check if we should fallback
            if not self.is_service_unavailable_error(error):
                self._logger.error("Primary provider %s failed (not a service error): %s", primary, error)
                raise
            
            self._logger.warning(
                "Primary provider %s unavailable, trying fallback %s: %s",
                primary, backup, error
            )
            
            # Try backup provider
            try:
                result = await generate_with(backup)
                self._logger.info("Generation started with fallback provider: %s", backup)
                return result
                
            except Exception as backup_error:
                self._logger.error(
                    "Both providers failed. Primary (%s): %s, Backup (%s): %s",
                    primary, error, backup, backup_error
                )
                raise RuntimeError(f"Both providers unavailable. {backup_error}")
