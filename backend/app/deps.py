"""API auth: X-API-Key for the bot, Bearer admin token for the dashboard."""

import secrets

from fastapi import Header, HTTPException, status

from .config import settings
from .services.security import verify_admin_token


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    if x_api_key and secrets.compare_digest(x_api_key, settings.API_KEY):
        return "api-key"
    if authorization and authorization.lower().startswith("bearer "):
        if verify_admin_token(authorization[7:].strip()):
            return "admin"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API key",
    )
