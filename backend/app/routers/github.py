"""GitHub repo prefill for the dashboard 'Add from GitHub URL' button."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import settings
from ..deps import require_api_key
from ..services.github import fetch_repo_prefill

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/prefill")
async def prefill(
    url: str = Query(...),
    _auth: str = Depends(require_api_key),
):
    try:
        return await fetch_repo_prefill(url, settings.GITHUB_TOKEN)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub request failed: {exc}")
