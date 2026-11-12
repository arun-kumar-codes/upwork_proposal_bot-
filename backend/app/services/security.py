"""Admin session tokens (stdlib HMAC, no extra dependency)."""

import base64
import hashlib
import hmac
import json
import time

from ..config import settings


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_admin_token() -> tuple[str, int]:
    exp = int(time.time()) + settings.ADMIN_TOKEN_DAYS * 86400
    body = _b64encode(json.dumps({"sub": "admin", "exp": exp}).encode())
    sig = _b64encode(
        hmac.new(settings.API_KEY.encode(), body.encode(), hashlib.sha256).digest()
    )
    return f"{body}.{sig}", exp


def verify_admin_token(token: str) -> bool:
    try:
        body, sig = token.split(".", 1)
        expected = _b64encode(
            hmac.new(settings.API_KEY.encode(), body.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return False
        payload = json.loads(_b64decode(body))
        return payload.get("sub") == "admin" and int(payload.get("exp", 0)) > time.time()
    except Exception:
        return False
