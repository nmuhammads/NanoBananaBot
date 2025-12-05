import aiohttp
import logging
from typing import Optional, List, Dict, Any


class SeedreamClient:
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout_seconds: int = 60,
        callback_url: Optional[str] = None,
    ):
        # Sanitize base URL (remove trailing slashes/spaces/commas)
        self.base_url = base_url.rstrip(",/ ")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.callback_url = callback_url
        self._logger = logging.getLogger("seedream.api")

    async def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
        image_size: Optional[str] = None,
        image_resolution: Optional[str] = None,
        quality: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        max_images: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Calls Seedream (KIE) API to create a generation task.

        Returns: URL to the generated image if synchronous; otherwise raises
        RuntimeError with 'awaiting callback' when taskId is returned.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Build payload according to KIE API (createTask)
        # https://api.kie.ai/api/v1/jobs/createTask
        payload: Dict[str, Any] = {}
        # Model is required; default stays empty unless provided by caller
        payload["model"] = model or "bytedance/seedream-v4-text-to-image"
        if self.callback_url:
            payload["callBackUrl"] = self.callback_url
        input_obj: Dict[str, Any] = {"prompt": prompt}
        # Seedream V4 (KIE) input mapping
        is_seedream = isinstance(payload.get("model"), str) and "seedream" in str(payload.get("model")).lower()
        if is_seedream:
            if aspect_ratio:
                input_obj["aspect_ratio"] = aspect_ratio
            # Only send image_size if aspect_ratio is NOT set, or if we want to support both (usually mutually exclusive)
            elif image_size:
                input_obj["image_size"] = image_size
            
            if image_resolution:
                input_obj["image_resolution"] = image_resolution
            if quality:
                input_obj["quality"] = quality
            if isinstance(max_images, int) and 1 <= max_images <= 6:
                input_obj["max_images"] = max_images
            # KIE API expects 'image_urls' for edit flows when a reference image is provided
            if image_urls:
                input_obj["image_urls"] = image_urls
        else:
            # Fallback for non-Seedream models (kept for compatibility)
            if image_size:
                input_obj["image_size"] = image_size
            if image_urls:
                input_obj["image_urls"] = image_urls
        payload["input"] = input_obj
        if meta:
            payload["meta"] = meta

        # Endpoint selection: KIE API vs legacy
        if "api.kie.ai" in self.base_url or "/api/v1" in self.base_url:
            url = f"{self.base_url.rstrip('/')}/jobs/createTask"
        else:
            # Legacy/simple provider path
            url = f"{self.base_url}/generate"

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        self._logger.info("Requesting Seedream generate: url=%s, payload_keys=%s", url, list(payload.keys()))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    status = resp.status
                    text = await resp.text()
                    self._logger.debug("Seedream response status=%s body=%s", status, text[:500])
                    resp.raise_for_status()
                    try:
                        data = await resp.json()
                    except Exception:
                        self._logger.error("Failed to parse JSON, response text snippet: %s", text[:500])
                        raise
                    # KIE may return {code,msg,data}; surface errors if code != 200
                    if isinstance(data, dict) and "code" in data and data.get("code") not in (200, 0, None):
                        self._logger.error("KIE API error: code=%s msg=%s", data.get("code"), data.get("msg"))
                        raise RuntimeError(f"KIE API error: {data.get('msg')}")
                    # Two possible patterns:
                    # 1) Synchronous: returns image_url
                    # 2) Async: returns taskId and will POST to callBackUrl later
                    image_url = (
                        data.get("image_url")
                        or data.get("imageUrl")
                        or (data.get("data") or {}).get("imageUrl")
                    )
                    # Some KIE image APIs (incl. Seedream) may return an array of result URLs
                    if not image_url:
                        result_urls = (
                            data.get("resultUrls")
                            or (data.get("data") or {}).get("resultUrls")
                        )
                        if isinstance(result_urls, list) and result_urls:
                            image_url = result_urls[0]
                    if image_url:
                        self._logger.info("Seedream image_url received: %s", image_url)
                        return image_url

                    task_id = data.get("taskId") or data.get("id") or data.get("data", {}).get("taskId")
                    if task_id:
                        self._logger.info("Seedream task accepted, id=%s (await callback)", task_id)
                        # For async flow, we cannot return image_url immediately.
                        # Let the caller handle user messaging; raise a distinct error.
                        raise RuntimeError("Seedream API accepted task; awaiting callback")

                    # No image_url and no task id — likely an error payload with 'msg'
                    self._logger.error("Seedream API missing image_url and taskId in response: %s", data)
                    raise RuntimeError("Seedream API did not return image_url")
        except aiohttp.ClientError as e:
            self._logger.exception("HTTP client error during Seedream request: %s", e)
            raise
        except Exception as e:
            self._logger.exception("Unexpected error during Seedream request: %s", e)
            raise

    async def get_record_info(self, task_id: str) -> Dict[str, Any]:
        """
        Queries KIE API for task status. Returns parsed JSON dict.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Endpoint for recordInfo
        if "api.kie.ai" in self.base_url or "/api/v1" in self.base_url:
            url = f"{self.base_url.rstrip('/')}/jobs/recordInfo"
        else:
            url = f"{self.base_url}/recordInfo"

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        params = {"taskId": task_id}
        self._logger.info("Querying KIE recordInfo: url=%s taskId=%s", url, task_id)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    status = resp.status
                    text = await resp.text()
                    self._logger.debug("KIE recordInfo response status=%s body=%s", status, text[:500])
                    resp.raise_for_status()
                    try:
                        data = await resp.json()
                    except Exception:
                        self._logger.error("Failed to parse JSON, response text snippet: %s", text[:500])
                        raise
                    if isinstance(data, dict) and "code" in data and data.get("code") not in (200, 0, None):
                        self._logger.error("KIE recordInfo error: code=%s msg=%s", data.get("code"), data.get("msg"))
                        raise RuntimeError(f"KIE recordInfo error: {data.get('msg')}")
                    return data
        except aiohttp.ClientError as e:
            self._logger.exception("HTTP client error during KIE recordInfo: %s", e)
            raise
        except Exception as e:
            self._logger.exception("Unexpected error during KIE recordInfo: %s", e)
            raise