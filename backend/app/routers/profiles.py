"""Profile CRUD plus name-based lookup for the bot."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import require_api_key
from ..models import Profile, Project
from ..schemas import (
    ProfileCreate,
    ProfileRead,
    ProfileUpdate,
    ProfileWithProjects,
    ProjectSummary,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _with_projects(db: Session, profile: Profile) -> ProfileWithProjects:
    base = ProfileRead.model_validate(profile)
    active = [ProjectSummary.model_validate(p) for p in profile.projects if p.status == "active"]
    return ProfileWithProjects(**base.model_dump(), active_projects=active)


@router.get("", response_model=list[ProfileRead])
def list_profiles(
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    return (
        db.query(Profile)
        .options(selectinload(Profile.projects))
        .order_by(Profile.name)
        .all()
    )


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    existing = (
        db.query(Profile).filter(func.lower(Profile.name) == payload.name.lower()).first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists")
    profile = Profile(
        name=payload.name,
        intro=payload.intro,
        skills=payload.skills,
        tone=payload.tone,
        portfolio_url=payload.portfolio_url,
        signature=payload.signature,
    )
    db.add(profile)
    db.flush()
    if payload.project_ids:
        projects = db.query(Project).filter(Project.id.in_(payload.project_ids)).all()
        if len(projects) != len(set(payload.project_ids)):
            raise HTTPException(status_code=404, detail="One or more project ids not found")
        profile.projects = projects
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{key}", response_model=ProfileWithProjects)
def get_profile(
    key: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    query = db.query(Profile).options(selectinload(Profile.projects))
    profile = None
    if key.isdigit():
        profile = query.filter(Profile.id == int(key)).first()
    if profile is None:
        profile = query.filter(func.lower(Profile.name) == key.strip().lower()).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _with_projects(db, profile)


@router.put("/{profile_id}", response_model=ProfileRead)
@router.patch("/{profile_id}", response_model=ProfileRead)
def update_profile(
    profile_id: int,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    profile = (
        db.query(Profile)
        .options(selectinload(Profile.projects))
        .filter(Profile.id == profile_id)
        .first()
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    data = payload.model_dump(exclude_unset=True)
    project_ids = data.pop("project_ids", None)
    if "name" in data and data["name"] is not None:
        clash = (
            db.query(Profile)
            .filter(func.lower(Profile.name) == data["name"].lower())
            .filter(Profile.id != profile_id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=409, detail="Profile name already exists")
    for key, value in data.items():
        setattr(profile, key, value)
    if project_ids is not None:
        projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
        if len(projects) != len(set(project_ids)):
            raise HTTPException(status_code=404, detail="One or more project ids not found")
        profile.projects = projects
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(profile)
    db.commit()
    return None
