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

    async def generate_image(self, prompt: str, model: str = "bytedance/seedream-v4.5-text-to-image", status_callback=None, **kwargs) -> str:
        """Generates an image using Wavespeed API with polling."""
        url = f"{self.base_url}/{model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "images": kwargs.get("images", []),
            "size": kwargs.get("size", "2K").replace("x", "*"), # Ensure * separator
            "enable_sync_mode": False, # Async mode for status updates
            "enable_safety_checker": False
        }
        
        self._logger.info("Requesting Wavespeed generation (async): model=%s", model)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)) as session:
                # 1. Submit task
                async with session.post(url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    # Response: {"data": {"id": "..."}}
                    request_id = data.get("data", {}).get("id")
                    if not request_id:
                        raise RuntimeError(f"No request ID in Wavespeed response: {data}")
                
                # 2. Poll for results
                poll_url = f"https://api.wavespeed.ai/api/v3/predictions/{request_id}/result"
                start_time = asyncio.get_running_loop().time()
                
                while True:
                    if asyncio.get_running_loop().time() - start_time > self.timeout_seconds:
                        raise RuntimeError("Wavespeed generation timed out")
                    
                    async with session.get(poll_url, headers=headers) as resp:
                        if resp.status != 200:
                            self._logger.warning("Wavespeed poll error: %s", resp.status)
                            await asyncio.sleep(1)
                            continue
                            
                        data = await resp.json()
                        result = data.get("data", {})
                        status = result.get("status")
                        
                        if status_callback:
                            await status_callback(status)
                        
                        if status == "completed":
                            outputs = result.get("outputs", [])
                            if outputs:
                                return outputs[0]
                            raise RuntimeError(f"No outputs in completed Wavespeed task: {result}")
                        elif status == "failed":
                            raise RuntimeError(f"Wavespeed task failed: {result.get('error')}")
                        
                        await asyncio.sleep(1)

        except Exception as e:
            self._logger.error("Wavespeed generation failed: %s", e)
            raise

class ReplicateClient:
    def __init__(self, api_token: str, timeout_seconds: int = 60):
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds
        self._logger = logging.getLogger("replicate.api")

    async def generate_image(self, prompt: str, model: str = "bytedance/seedream-4.5", status_callback=None, **kwargs) -> str:
        """Generates an image using Replicate API via HTTP with polling."""
        # Using the predictions endpoint
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            # "Prefer": "wait" # Removed to allow polling
        }
        
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

        self._logger.info("Requesting Replicate generation (async): model=%s", model)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)) as session:
                # 1. Create prediction
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status not in (200, 201):
                        text = await resp.text()
                        raise RuntimeError(f"Replicate API error: {resp.status} {text}")
                    
                    data = await resp.json()
                    get_url = data.get("urls", {}).get("get")
                    if not get_url:
                        raise RuntimeError("No get URL in Replicate response")

                # 2. Poll for results
                start_time = asyncio.get_running_loop().time()
                while True:
                    if asyncio.get_running_loop().time() - start_time > self.timeout_seconds:
                        raise RuntimeError("Replicate task timed out")
                        
                    async with session.get(get_url, headers=headers) as get_resp:
                        if get_resp.status != 200:
                            self._logger.warning("Replicate poll error: %s", get_resp.status)
                            await asyncio.sleep(1)
                            continue
                            
                        get_data = await get_resp.json()
                        status = get_data.get("status")
                        
                        if status_callback:
                            await status_callback(status)
                            
                        if status == "succeeded":
                            output = get_data.get("output")
                            if isinstance(output, list) and output:
                                return output[0]
                            return str(output)
                        elif status == "failed":
                            raise RuntimeError(f"Replicate task failed: {get_data.get('error')}")
                        elif status == "canceled":
                            raise RuntimeError("Replicate task canceled")
                            
                        await asyncio.sleep(1)

        except Exception as e:
            self._logger.error("Replicate generation failed: %s", e)
            raise

class UnifiedClient:
    def __init__(self, wavespeed_key: Optional[str], replicate_key: Optional[str]):
        self.wavespeed = WavespeedClient(wavespeed_key) if wavespeed_key else None
        self.replicate = ReplicateClient(replicate_key) if replicate_key else None
        self._logger = logging.getLogger("unified.client")

    async def generate_seedream_4_5(self, prompt: str, model_type: str = "t2i", status_callback=None, **kwargs) -> str:
        ratio = kwargs.get("ratio", "1:1")
        if ratio == "auto":
            ratio = "1:1" # Default fallback

        # Map ratio to Wavespeed size (approx 2K/4K logic or fixed)
        # User requested max possible for 4K (up to 4096px) for Wavespeed
        # and fixed "size": "2K", "aspect_ratio": "match_input_image" for Replicate
        
        # Wavespeed: use 3072*4096 (3:4 aspect ratio, safe high res, use * separator)
        ws_size = "3072*4096"

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
                    
                    # UnifiedClient receives image_urls, WavespeedClient expects images
                    # We pass image_urls as images to WavespeedClient
                    return await self.wavespeed.generate_image(
                        prompt, 
                        model=ws_model,
                        size=ws_size,
                        images=kwargs.get("image_urls", []),
                        status_callback=status_callback,
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
                status_callback=status_callback,
                **kwargs
            )
        
        raise RuntimeError("No available provider for Seedream 4.5 (Wavespeed low balance/failed, Replicate not configured)")
