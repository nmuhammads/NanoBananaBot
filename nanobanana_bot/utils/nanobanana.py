import aiohttp
import logging
from typing import Optional, List, Dict, Any


class NanoBananaClient:
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
    ) -> str:
        """
        Calls NanoBanana API to generate an image.

        Returns: URL to the generated image.
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

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
        if (payload.get("model") == "nano-banana-pro"):
            if image_size:
                input_obj["aspect_ratio"] = image_size
            if image_urls:
                input_obj["image_input"] = list(input_obj.get("image_urls", []))
            if "resolution" not in input_obj:
                input_obj["resolution"] = "4K"
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