"""
Piapi Client - Резервный API провайдер для NanoBanana Pro.
Предоставляет fallback при недоступности основного провайдера (Kie.ai).
"""

import aiohttp
import logging
from typing import Optional, List, Dict, Any


PIAPI_BASE_URL = "https://api.piapi.ai"


class PiapiClient:
    """Client for Piapi NanoBanana Pro API (fallback provider)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: int = 60,
        callback_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        # Sanitize callback URL
        self.callback_url = (
            str(callback_url).strip().strip("`").rstrip(",/ ")
            if callback_url else None
        )
        self._logger = logging.getLogger("nanobanana.piapi")

    async def create_task(
        self,
        prompt: str,
        image_urls: Optional[List[str]] = None,
        aspect_ratio: Optional[str] = None,
        resolution: str = "2K",
        output_format: str = "png",
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Creates generation task via Piapi API.
        
        Returns: task_id string.
        """
        if not self.api_key:
            raise RuntimeError("PIAPI_API_KEY is not configured")

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        # Build input object
        input_obj: Dict[str, Any] = {
            "prompt": prompt,
            "output_format": output_format,
            "resolution": resolution,
            "safety_level": "low",  # Always low for NanoBanana Pro
        }

        # Add image_urls if provided (Piapi uses image_urls, not image_input)
        if image_urls:
            cleaned_urls = [
                str(u).strip().strip("`").strip('"').strip("'")
                for u in image_urls
            ]
            input_obj["image_urls"] = cleaned_urls

        # Add aspect_ratio only if not Auto/None
        if aspect_ratio and aspect_ratio.lower() != "auto":
            input_obj["aspect_ratio"] = aspect_ratio

        # Build request body
        body: Dict[str, Any] = {
            "model": "gemini",
            "task_type": "nano-banana-pro",
            "input": input_obj,
        }

        # Add webhook config if callback URL available
        if self.callback_url:
            cb_url = self.callback_url
            # Append meta params to callback URL if available
            if meta:
                try:
                    from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
                    parsed = urlparse(str(cb_url))
                    qs = dict(parse_qsl(parsed.query))
                    if meta.get("generationId") is not None:
                        qs["generationId"] = str(meta.get("generationId"))
                    if meta.get("userId") is not None:
                        qs["userId"] = str(meta.get("userId"))
                    new_query = urlencode(qs)
                    cb_url = urlunparse(parsed._replace(query=new_query))
                except Exception:
                    pass
            
            body["config"] = {
                "webhook_config": {"endpoint": cb_url}
            }

        self._logger.info(
            "Piapi creating task: prompt_len=%s, has_images=%s, resolution=%s",
            len(prompt), bool(image_urls), resolution
        )

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{PIAPI_BASE_URL}/api/v1/task",
                    json=body,
                    headers=headers
                ) as resp:
                    status = resp.status
                    text = await resp.text()
                    self._logger.debug("Piapi response status=%s body=%s", status, text[:500])

                    if status != 200:
                        self._logger.error("Piapi task create failed: status=%s body=%s", status, text[:300])
                        raise RuntimeError(f"Piapi API error: {status} - {text[:200]}")

                    try:
                        data = await resp.json()
                    except Exception:
                        self._logger.error("Failed to parse Piapi JSON response: %s", text[:500])
                        raise RuntimeError("Invalid JSON from Piapi")

                    # Check response code
                    if data.get("code") != 200:
                        msg = data.get("message") or "Unknown error"
                        self._logger.error("Piapi error: code=%s msg=%s", data.get("code"), msg)
                        raise RuntimeError(f"Piapi: {msg}")

                    task_id = data.get("data", {}).get("task_id")
                    if not task_id:
                        self._logger.error("Piapi response missing task_id: %s", data)
                        raise RuntimeError("Piapi response missing task_id")

                    self._logger.info("Piapi task created: id=%s", task_id)
                    return task_id

        except aiohttp.ClientError as e:
            self._logger.exception("HTTP client error during Piapi request: %s", e)
            raise
        except Exception as e:
            self._logger.exception("Unexpected error during Piapi request: %s", e)
            raise

    async def check_task(self, task_id: str) -> Dict[str, Any]:
        """
        Check task status via Piapi API.
        
        Returns dict with keys: status, image_url (if completed), error (if failed).
        """
        if not self.api_key:
            raise RuntimeError("PIAPI_API_KEY is not configured")

        headers = {"X-API-Key": self.api_key}
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{PIAPI_BASE_URL}/api/v1/task/{task_id}",
                    headers=headers
                ) as resp:
                    data = await resp.json()

                    if data.get("code") != 200:
                        return {
                            "status": "failed",
                            "error": data.get("message", "Unknown error"),
                        }

                    task_data = data.get("data", {})
                    status = task_data.get("status", "").lower()

                    result: Dict[str, Any] = {"status": status}

                    if status == "completed":
                        output = task_data.get("output", {})
                        image_url = output.get("image_url") or (output.get("image_urls") or [None])[0]
                        result["image_url"] = image_url

                    if status == "failed":
                        error = task_data.get("error", {})
                        result["error"] = error.get("message", "Generation failed")

                    return result

        except aiohttp.ClientError as e:
            self._logger.exception("HTTP error checking Piapi task: %s", e)
            return {"status": "error", "error": str(e)}
        except Exception as e:
            self._logger.exception("Error checking Piapi task: %s", e)
            return {"status": "error", "error": str(e)}

    async def poll_task(self, task_id: str, timeout_ms: int = 600000) -> str:
        """
        Poll Piapi task until completion or timeout.
        
        Returns: image_url on success, 'TIMEOUT' on timeout.
        Raises: RuntimeError on failure.
        """
        import asyncio
        import time

        start = time.time()
        timeout_sec = timeout_ms / 1000
        poll_interval = 30  # Piapi recommends 30 second intervals

        self._logger.info("Polling Piapi task %s (timeout: %sms)", task_id, timeout_ms)

        while time.time() - start < timeout_sec:
            result = await self.check_task(task_id)
            status = result.get("status", "")

            if status == "completed":
                image_url = result.get("image_url")
                if image_url:
                    self._logger.info("Piapi task %s completed", task_id)
                    return image_url
                else:
                    raise RuntimeError("Piapi task completed but no image_url")

            if status == "failed":
                error_msg = result.get("error", "Generation failed")
                self._logger.error("Piapi task %s failed: %s", task_id, error_msg)
                raise RuntimeError(error_msg)

            await asyncio.sleep(poll_interval)

        self._logger.warning("Piapi task %s timed out", task_id)
        return "TIMEOUT"
