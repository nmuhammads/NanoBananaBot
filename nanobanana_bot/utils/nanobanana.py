import aiohttp
import logging
from typing import Optional


class NanoBananaClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout_seconds: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._logger = logging.getLogger("nanobanana.api")

    async def generate_image(self, prompt: str, style: Optional[str] = None, seed: Optional[int] = None) -> str:
        """
        Calls NanoBanana API to generate an image.

        Returns: URL to the generated image.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"prompt": prompt}
        if style:
            payload["style"] = style
        if seed is not None:
            payload["seed"] = seed

        # Assuming endpoint path; adjust if API differs
        url = f"{self.base_url}/generate"

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        self._logger.info("Requesting NanoBanana generate: url=%s, payload_keys=%s", url, list(payload.keys()))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    status = resp.status
                    text = await resp.text()
                    self._logger.debug("NanoBanana response status=%s body=%s", status, text[:500])
                    resp.raise_for_status()
                    try:
                        data = await resp.json()
                    except Exception:
                        self._logger.error("Failed to parse JSON, response text snippet: %s", text[:500])
                        raise
                    # Expecting response to contain 'image_url'
                    image_url = data.get("image_url")
                    if not image_url:
                        self._logger.error("NanoBanana API missing image_url in response: %s", data)
                        raise RuntimeError("NanoBanana API did not return image_url")
                    self._logger.info("NanoBanana image_url received: %s", image_url)
                    return image_url
        except aiohttp.ClientError as e:
            self._logger.exception("HTTP client error during NanoBanana request: %s", e)
            raise
        except Exception as e:
            self._logger.exception("Unexpected error during NanoBanana request: %s", e)
            raise