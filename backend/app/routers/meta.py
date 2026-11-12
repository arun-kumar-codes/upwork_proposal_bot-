"""Bot contract meta: categories + lightweight profile list."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import require_api_key
from ..models import Profile, Project

router = APIRouter(tags=["meta"])


@router.get("/categories", response_model=list[str])
def list_categories(
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    rows = (
        db.query(Project.category)
        .filter(Project.category != "")
        .distinct()
        .all()
    )
    return sorted({row[0].strip().lower() for row in rows if row[0] and row[0].strip()})


@router.get("/meta/profiles")
def list_meta_profiles(
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    profiles = (
        db.query(Profile)
        .options(selectinload(Profile.projects))
        .order_by(Profile.name)
        .all()
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "skills": p.skills,
            "tone": p.tone,
            "portfolio_url": p.portfolio_url,
            "project_count": len(p.projects),
            "active_project_count": sum(1 for x in p.projects if x.status == "active"),
        }
        for p in profiles
    ]
