# Alias entrypoint for uvicorn/Railway
# Delegates to the main FastAPI app defined in nanobanana_bot.webapp

from nanobanana_bot.webapp import app  # re-export

__all__ = ["app"]