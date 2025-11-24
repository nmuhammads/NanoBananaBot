import aiohttp
import logging
import base64
from typing import Optional, List, Dict, Any


class NanoBananaClient:
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        pro_api_key: Optional[str] = None,
        timeout_seconds: int = 60,
        callback_url: Optional[str] = None,
    ):
        # Sanitize base URL (remove trailing slashes/spaces/commas)
        self.base_url = base_url.rstrip(",/ ")
        self.api_key = api_key
        self.pro_api_key = pro_api_key
        self.timeout_seconds = timeout_seconds
        # Sanitize callback URL: trim spaces/backticks and trailing commas/slashes
        self.callback_url = (
            str(callback_url).strip().strip("`").rstrip(",/ ")
            if callback_url else None
        )
        self._logger = logging.getLogger("nanobanana.api")

    async def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
        image_size: Optional[str] = None,
        output_format: Optional[str] = "png",
        meta: Optional[Dict[str, Any]] = None,
    ) -> str | bytes:
        """
        Calls NanoBanana API to generate an image.

        Returns: URL to the generated image (str) OR image bytes (bytes) for Pro model.
        """
        headers = {"Content-Type": "application/json"}
        
        # Determine which key to use
        is_pro = (model == "nano-banana-pro" or model == "gemini-3-pro-image-preview")
        token = self.pro_api_key if (is_pro and self.pro_api_key) else self.api_key
        
        if token:
            headers["Authorization"] = f"Bearer {token}"

        # --- NanoBanana Pro Implementation (New API) ---
        # --- NanoBanana Pro Implementation (New API v2) ---
        if is_pro:
            # Endpoint: generateContent
            # Docs: https://api.apiyi.com/v1beta/models/gemini-3-pro-image-preview:generateContent
            # We try to respect base_url if it matches the provider, otherwise use the doc's default.
            if "apiyi.com" in self.base_url:
                 url = f"{self.base_url.rstrip('/')}/v1beta/models/gemini-3-pro-image-preview:generateContent"
            else:
                 # Default to the doc's endpoint if base_url is legacy
                 url = "https://api.apiyi.com/v1beta/models/gemini-3-pro-image-preview:generateContent"

            # Prepare parts
            parts = []
            
            # 1. Handle Input Images (Download & Convert to Base64)
            if image_urls:
                self._logger.info("Downloading %d images for Pro generation...", len(image_urls))
                async with aiohttp.ClientSession() as img_session:
                    for img_url in image_urls:
                        try:
                            # Clean URL
                            clean_url = str(img_url).strip().strip("`").strip('"').strip("'")
                            async with img_session.get(clean_url) as img_resp:
                                if img_resp.status == 200:
                                    img_data = await img_resp.read()
                                    b64_img = base64.b64encode(img_data).decode("utf-8")
                                    
                                    # Determine mime type (simple heuristic)
                                    mime_type = "image/png"
                                    if clean_url.lower().endswith(".jpg") or clean_url.lower().endswith(".jpeg"):
                                        mime_type = "image/jpeg"
                                    elif clean_url.lower().endswith(".webp"):
                                        mime_type = "image/webp"
                                        
                                    parts.append({
                                        "inline_data": {
                                            "mime_type": mime_type,
                                            "data": b64_img
                                        }
                                    })
                                else:
                                    self._logger.warning("Failed to download image %s: status %s", clean_url, img_resp.status)
                        except Exception as e:
                            self._logger.warning("Error downloading image %s: %s", img_url, e)

            # 2. Add Text Prompt
            if prompt:
                parts.append({"text": prompt})

            # 3. Construct Payload
            # Map image_size (e.g., "16:9") to aspectRatio
            # If image_size is "auto" or None, we might default or omit.
            # Docs example uses "16:9".
            
            generation_config = {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "image_size": "4K" # Default to 4K for Pro
                }
            }
            
            if image_size and image_size != "auto":
                generation_config["imageConfig"]["aspectRatio"] = image_size

            payload = {
                "contents": [
                    {
                        "parts": parts
                    }
                ],
                "generationConfig": generation_config
            }

            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            self._logger.info("Requesting NanoBanana Pro (v2): url=%s model=%s ratio=%s", url, model, image_size)
            
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as resp:
                        status = resp.status
                        text = await resp.text()
                        self._logger.debug("NanoBanana Pro response status=%s body_len=%s", status, len(text))
                        
                        if status != 200:
                            self._logger.error("NanoBanana Pro API error: status=%s body=%s", status, text[:500])
                            raise RuntimeError(f"NanoBanana Pro API error: {status} - {text[:200]}")
                            
                        try:
                            data = await resp.json()
                        except Exception:
                             import json
                             data = json.loads(text)

                        # Parse response (v2 format)
                        # candidates[0].content.parts[...].inlineData.data
                        if "candidates" not in data or not data["candidates"]:
                             raise RuntimeError("NanoBanana Pro API returned no candidates")
                        
                        candidate = data["candidates"][0]
                        content_parts = candidate.get("content", {}).get("parts", [])
                        
                        b64_data = None
                        
                        for part in content_parts:
                            if "inlineData" in part:
                                b64_data = part["inlineData"]["data"]
                                break
                            elif "inline_data" in part:
                                b64_data = part["inline_data"]["data"]
                                break
                        
                        if not b64_data:
                            self._logger.error("Could not find inlineData in response parts: %s", content_parts)
                            raise RuntimeError("NanoBanana Pro API response did not contain valid image data")
                            
                        # Decode
                        try:
                            image_bytes = base64.b64decode(b64_data)
                            if len(image_bytes) < 100:
                                raise ValueError("Decoded image too small")
                            return image_bytes
                        except Exception as e:
                            raise RuntimeError(f"Failed to decode Base64 image: {e}")

            except Exception as e:
                self._logger.exception("Error during NanoBanana Pro request: %s", e)
                raise

        # --- End NanoBanana Pro Implementation ---

        # Build payload according to KIE API (createTask)
        # https://api.kie.ai/api/v1/jobs/createTask
        payload: Dict[str, Any] = {}
        # Model: text-only uses 'google/nano-banana', edit uses 'google/nano-banana-edit'
        payload["model"] = model or "google/nano-banana"
        if self.callback_url:
            # Если meta содержит идентификаторы, добавим их в query строки callback URL,
            # чтобы надёжно восстановить контекст в обработчике.
            cb_url = self.callback_url
            try:
                if meta and (meta.get("generationId") is not None or meta.get("userId") is not None):
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
                # В случае ошибки формирования URL — используем исходный
                pass
            payload["callBackUrl"] = cb_url
        input_obj: Dict[str, Any] = {"prompt": prompt}
        if output_format:
            input_obj["output_format"] = output_format
        if image_size:
            input_obj["image_size"] = image_size
        if image_urls:
            cleaned_urls: List[str] = []
            for u in image_urls:
                su = str(u).strip().strip("`").strip('"').strip("'")
                cleaned_urls.append(su)
            input_obj["image_urls"] = cleaned_urls
        
        # Legacy Pro handling (removed or kept? The user said "connect it ONLY for NanoBanana Pro", implying replacing the old logic for Pro)
        # The old logic for "nano-banana-pro" inside this block was:
        # if (payload.get("model") == "nano-banana-pro"): ...
        # We have handled "nano-banana-pro" above in the new block and returned early.
        # So we don't need to worry about it here, but let's clean up if needed.
        # Actually, if we fall through here, it means model != "nano-banana-pro".
        # So the old logic for "nano-banana-pro" inside this block is dead code effectively, which is fine.

        payload["input"] = input_obj
        if meta:
            payload["meta"] = meta

        # Endpoint selection
        if "api.kie.ai" in self.base_url or "/api/v1" in self.base_url:
            url = f"{self.base_url.rstrip('/')}/jobs/createTask"
        else:
            # Legacy/simple provider path
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
                    if image_url:
                        self._logger.info("NanoBanana image_url received: %s", image_url)
                        return image_url

                    task_id = data.get("taskId") or data.get("id") or data.get("data", {}).get("taskId")
                    if task_id:
                        self._logger.info("NanoBanana task accepted, id=%s (await callback)", task_id)
                        # For async flow, we cannot return image_url immediately.
                        # Let the caller handle user messaging; raise a distinct error.
                        raise RuntimeError("NanoBanana API accepted task; awaiting callback")

                    # No image_url and no task id — likely an error payload with 'msg'
                    self._logger.error("NanoBanana API missing image_url and taskId in response: %s", data)
                    raise RuntimeError("NanoBanana API did not return image_url")
        except aiohttp.ClientError as e:
            self._logger.exception("HTTP client error during NanoBanana request: %s", e)
            raise
        except Exception as e:
            self._logger.exception("Unexpected error during NanoBanana request: %s", e)
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