import aiohttp
from typing import Optional


class NanoBananaClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout_seconds: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

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
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                # Expecting response to contain 'image_url'
                image_url = data.get("image_url")
                if not image_url:
                    raise RuntimeError("NanoBanana API did not return image_url")
                return image_url