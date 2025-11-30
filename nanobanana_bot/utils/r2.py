import os
import aioboto3
import logging
from botocore.config import Config
from uuid import uuid4
import mimetypes

_logger = logging.getLogger("r2_client")

class R2Client:
    def __init__(self):
        self.account_id = os.getenv("R2_ACCOUNT_ID")
        self.access_key_id = os.getenv("R2_ACCESS_KEY_ID")
        self.secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("R2_BUCKET_NAME")
        self.public_url = os.getenv("R2_PUBLIC_URL")

        if not all([self.account_id, self.access_key_id, self.secret_access_key, self.bucket_name, self.public_url]):
            _logger.warning("R2 credentials are incomplete. R2 uploads will fail.")

        self.endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"
        self.session = aioboto3.Session()

    async def upload_file_from_bytes(self, file_bytes: bytes, content_type: str = "image/png") -> str | None:
        """
        Uploads bytes to R2 and returns the public URL.
        """
        if not self.bucket_name:
            return None

        ext = mimetypes.guess_extension(content_type) or ".png"
        filename = f"{uuid4().hex}{ext}"

        try:
            async with self.session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name="auto",  # R2 requires region to be 'auto' or specific, but 'auto' is common
                config=Config(signature_version="s3v4"),
            ) as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=filename,
                    Body=file_bytes,
                    ContentType=content_type,
                )
            
            return f"{self.public_url}/{filename}"
        except Exception as e:
            _logger.error(f"Failed to upload to R2: {e}")
            return None

    async def upload_file_from_url(self, url: str) -> str | None:
        """
        Downloads a file from a URL and uploads it to R2.
        """
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        _logger.error(f"Failed to download file from {url}: status {resp.status}")
                        return None
                    content = await resp.read()
                    content_type = resp.headers.get("Content-Type", "image/png")
            
            return await self.upload_file_from_bytes(content, content_type)
        except Exception as e:
            _logger.error(f"Failed to process URL upload for {url}: {e}")
            return None
