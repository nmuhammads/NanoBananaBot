import aiohttp
import logging
import asyncio
from typing import Optional, Dict, Any, List

class WavespeedClient:
    def __init__(self, api_key: str, timeout_seconds: int = 60):
        self.api_key = api_key
        self.base_url = "https://api.wavespeed.ai/api/v3"
        self.timeout_seconds = timeout_seconds
        self._logger = logging.getLogger("wavespeed.api")

    async def check_balance(self) -> float:
        """Checks the current balance on Wavespeed."""
        url = f"{self.base_url}/balance"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    # Response format: {"code": 200, "message": "success", "data": {"balance": 1.23}}
                    balance = data.get("data", {}).get("balance", 0.0)
                    self._logger.info("Wavespeed balance: %s", balance)
                    return float(balance)
        except Exception as e:
            self._logger.error("Failed to check Wavespeed balance: %s", e)
            return 0.0

    async def generate_image(self, prompt: str, model: str = "bytedance/seedream-v4.5-text-to-image", **kwargs) -> str:
        """Generates an image using Wavespeed API."""
        url = f"{self.base_url}/{model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "images": kwargs.get("images", []),
            "size": kwargs.get("size", "2K"), # Default to 2K as per docs
            "enable_sync_mode": True # We want the result directly if possible, or handle async if needed
        }
        
        self._logger.info("Requesting Wavespeed generation: model=%s", model)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    # Response format: {"outputs": ["url"], "status": "completed", ...}
                    outputs = data.get("outputs", [])
                    if outputs:
                        return outputs[0]
                    else:
                        raise RuntimeError(f"No outputs in Wavespeed response: {data}")
        except Exception as e:
            self._logger.error("Wavespeed generation failed: %s", e)
            raise

class ReplicateClient:
    def __init__(self, api_token: str, timeout_seconds: int = 60):
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds
        self._logger = logging.getLogger("replicate.api")

    async def generate_image(self, prompt: str, model: str = "bytedance/seedream-4.5", **kwargs) -> str:
        """Generates an image using Replicate API via HTTP."""
        # Using the predictions endpoint
        url = "https://api.replicate.com/v1/predictions"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Prefer": "wait" # Wait for the prediction to complete
        }
        
        # Determine version or model string. For public models, we can often pass the model name directly 
        # if the API supports it, or we need the version hash. 
        # The docs say "bytedance/seedream-4.5" is the model. 
        # We might need to look up the version, but let's try with the model name if the client library does it, 
        # but here we are using raw HTTP. 
        # Replicate API usually requires a version for `input` payload if not using the `models/{owner}/{name}/predictions` endpoint.
        # Let's use the `models` endpoint which is cleaner: https://api.replicate.com/v1/models/{model_owner}/{model_name}/predictions
        
        owner, name = model.split("/")
        url = f"https://api.replicate.com/v1/models/{owner}/{name}/predictions"

        payload = {
            "input": {
                "prompt": prompt,
                "size": kwargs.get("size", "2K"),
                "aspect_ratio": kwargs.get("aspect_ratio", "match_input_image"),
                "sequential_image_generation": "disabled",
                "max_images": 1
            }
        }
        # Map image_urls to image_input
        image_urls = kwargs.get("image_urls")
        if image_urls:
             payload["input"]["image_input"] = image_urls

        self._logger.info("Requesting Replicate generation: model=%s", model)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 201 or resp.status == 200:
                        data = await resp.json()
                        # If we used Prefer: wait, it might be completed.
                        status = data.get("status")
                        if status == "succeeded":
                            output = data.get("output")
                            if isinstance(output, list) and output:
                                return output[0]
                            elif isinstance(output, str):
                                return output
                        
                        # If not succeeded yet (or didn't wait long enough), we'd need to poll.
                        # For simplicity in this v1, let's assume 'Prefer: wait' works for reasonable times,
                        # or implement a simple poll loop if needed.
                        get_url = data.get("urls", {}).get("get")
                        if not get_url:
                             raise RuntimeError("No get URL in Replicate response")
                        
                        # Poll
                        for _ in range(30): # Poll for up to 30-60s more
                            await asyncio.sleep(2)
                            async with session.get(get_url, headers=headers) as get_resp:
                                get_data = await get_resp.json()
                                if get_data.get("status") == "succeeded":
                                    output = get_data.get("output")
                                    if isinstance(output, list) and output:
                                        return output[0]
                                    return str(output)
                                if get_data.get("status") == "failed":
                                    raise RuntimeError(f"Replicate task failed: {get_data.get('error')}")
                        raise RuntimeError("Replicate task timed out")

                    else:
                        text = await resp.text()
                        raise RuntimeError(f"Replicate API error: {resp.status} {text}")

        except Exception as e:
            self._logger.error("Replicate generation failed: %s", e)
            raise

class UnifiedClient:
    def __init__(self, wavespeed_key: Optional[str], replicate_key: Optional[str]):
        self.wavespeed = WavespeedClient(wavespeed_key) if wavespeed_key else None
        self.replicate = ReplicateClient(replicate_key) if replicate_key else None
        self._logger = logging.getLogger("unified.client")

    async def generate_seedream_4_5(self, prompt: str, model_type: str = "t2i", **kwargs) -> str:
        ratio = kwargs.get("ratio", "1:1")
        if ratio == "auto":
            ratio = "1:1" # Default fallback

        # Map ratio to Wavespeed size (approx 2K/4K logic or fixed)
        # User requested max possible for 4K (up to 4096px) for Wavespeed
        # and fixed "size": "2K", "aspect_ratio": "match_input_image" for Replicate
        
        # Wavespeed: use 3072x4096 (3:4 aspect ratio, max 4K)
        ws_size = "3072x4096"

        # 1. Try Wavespeed if configured and balance is sufficient
        if self.wavespeed:
            balance = await self.wavespeed.check_balance()
            if balance >= 0.04:
                try:
                    self._logger.info("Attempting Wavespeed generation (balance=%.2f)", balance)
                    # Determine Wavespeed model based on type
                    ws_model = "bytedance/seedream-v4.5-text-to-image"
                    if model_type == "edit":
                        ws_model = "bytedance/seedream-v4.5/edit"
                    
                    return await self.wavespeed.generate_image(
                        prompt, 
                        model=ws_model,
                        size=ws_size,
                        **kwargs
                    )
                except Exception as e:
                    self._logger.warning("Wavespeed generation failed, falling back: %s", e)
            else:
                self._logger.info("Wavespeed balance too low (%.2f < 0.04), skipping", balance)
        
        # 2. Fallback to Replicate
        if self.replicate:
            self._logger.info("Attempting Replicate generation")
            return await self.replicate.generate_image(
                prompt,
                model="bytedance/seedream-4.5",
                size="2K",
                aspect_ratio="match_input_image",
                **kwargs
            )
        
        raise RuntimeError("No available provider for Seedream 4.5 (Wavespeed low balance/failed, Replicate not configured)")
