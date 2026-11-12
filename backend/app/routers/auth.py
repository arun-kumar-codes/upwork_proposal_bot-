"""Dashboard admin login (single user, password from env)."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..config import settings
from ..deps import require_api_key
from ..services.security import create_admin_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginBody):
    if not secrets.compare_digest(body.password, settings.ADMIN_PASSWORD):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password"
        )
    token, exp = create_admin_token()
    return {"token": token, "expires_at": exp}


@router.get("/me")
def me(_auth: str = Depends(require_api_key)):
    return {"ok": True}
