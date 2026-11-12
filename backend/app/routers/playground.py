"""Test Playground: preview what the bot would reply to a client message."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..db import get_db
from ..deps import require_api_key
from ..models import PlaygroundRun, Profile, Project
from ..schemas import (
    PlaygroundHistoryItem,
    PlaygroundRunRequest,
    PlaygroundRunResult,
    ProjectSummary,
    SelectedProject,
)
from ..services.playground import (
    BotAuthError,
    BotNotConfiguredError,
    BotUnreachableError,
    call_real_bot,
    detect_category,
    generate_reply,
    select_projects,
)
from ..services.profile_names import is_valid_profile_name

router = APIRouter(prefix="/playground", tags=["playground"])


def _resolve_profile(db: Session, key: str) -> Profile:
    query = db.query(Profile).options(selectinload(Profile.projects))
    profile = None
    if key.isdigit():
        profile = query.filter(Profile.id == int(key)).first()
    if profile is None:
        profile = query.filter(func.lower(Profile.name) == key.strip().lower()).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.get("/config")
def get_config(_auth: str = Depends(require_api_key)):
    return {
        "simulated_enabled": bool(settings.openai_api_key),
        "real_bot_enabled": bool(settings.BOT_URL and settings.BOT_API_KEY),
    }


@router.get("/status")
def get_status(_auth: str = Depends(require_api_key)):
    return {
        "llm_configured": bool(settings.openai_api_key),
        "bot_configured": bool(settings.BOT_URL and settings.BOT_API_KEY),
        "github_configured": bool(settings.GITHUB_TOKEN),
        "llm_model": settings.LLM_MODEL,
    }


@router.post("/run", response_model=PlaygroundRunResult)
@router.post("/generate", response_model=PlaygroundRunResult)
async def run_playground(
    payload: PlaygroundRunRequest,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    profile = _resolve_profile(db, payload.profile)
    # Blank-profile buckets ("Not named", "Unknown", ...) exist in imported
    # data but are not freelancers: never generate or sign a proposal as them.
    if not is_valid_profile_name(profile.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid freelancer profile '{profile.name}': this looks like a "
                "placeholder, not a real person, so no proposal can be generated. "
                "Pick a real freelancer profile."
            ),
        )

    if payload.category_override:
        category: str | None = payload.category_override
        source = "override"
    else:
        categories = [
            row[0]
            for row in db.query(Project.category)
            .filter(Project.status == "active")
            .distinct()
            .all()
        ]
        category = detect_category(payload.client_message, categories)
        source = "detected" if category else "none"

    active = sorted(
        (p for p in profile.projects if p.status == "active"),
        key=lambda p: (p.updated_at, p.id),
        reverse=True,
    )
    picked = select_projects(
        active, category, payload.limit, client_message=payload.client_message
    )

    def _save_failed(error_text: str) -> None:
        db.add(
            PlaygroundRun(
                profile_name=profile.name,
                client_message=payload.client_message,
                category_override=payload.category_override,
                detected_category=category,
                category_source=source,
                selected=[
                    {"project_id": proj.id, "title": proj.title, "reason": reason}
                    for proj, reason in picked
                ],
                reply="",
                error=error_text,
                mode=payload.mode,
            )
        )
        db.commit()

    try:
        if payload.mode == "real_bot":
            reply = await call_real_bot(
                profile_name=profile.name,
                client_message=payload.client_message,
                category=category,
                projects=[p for p, _ in picked],
            )
        else:
            reply = await generate_reply(
                profile=profile,
                projects=[p for p, _ in picked],
                client_message=payload.client_message,
                category=category,
            )
    except BotAuthError as exc:
        _save_failed(str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    except BotNotConfiguredError as exc:
        _save_failed(str(exc))
        raise HTTPException(status_code=503, detail=str(exc))
    except BotUnreachableError as exc:
        _save_failed(str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        )
    except RuntimeError as exc:
        _save_failed(str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except httpx.HTTPError as exc:
        _save_failed(f"Bot unreachable: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Bot unreachable: {exc}"
        )

    run = PlaygroundRun(
        profile_name=profile.name,
        client_message=payload.client_message,
        category_override=payload.category_override,
        detected_category=category,
        category_source=source,
        selected=[
            {"project_id": p.id, "title": p.title, "reason": reason}
            for p, reason in picked
        ],
        reply=reply,
        mode=payload.mode,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return PlaygroundRunResult(
        run_id=run.id,
        detected_category=category,
        category_source=source,
        selected=[
            SelectedProject(project=ProjectSummary.model_validate(p), reason=reason)
            for p, reason in picked
        ],
        reply=reply,
        mode=payload.mode,
        created_at=run.created_at,
    )


@router.get("/history", response_model=list[PlaygroundHistoryItem])
def get_history(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    return (
        db.query(PlaygroundRun)
        .order_by(PlaygroundRun.created_at.desc(), PlaygroundRun.id.desc())
        .limit(limit)
        .all()
    )


@router.get("/history/{run_id}", response_model=PlaygroundHistoryItem)
def get_history_item(
    run_id: int,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    run = db.get(PlaygroundRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Playground run not found")
    return run
