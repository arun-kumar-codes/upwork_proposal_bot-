"""Project CRUD, bot filter endpoint, and status toggle."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import require_api_key
from ..models import Profile, Project
from ..schemas import ProjectCreate, ProjectRead, ProjectUpdate
from ..services.excel import get_or_create_profile

router = APIRouter(prefix="/projects", tags=["projects"])


def _resolve_profiles(
    db: Session,
    profile_ids: list[int] | None,
    profile_names: list[str] | None,
) -> list[Profile] | None:
    if profile_ids is None and profile_names is None:
        return None
    resolved: dict[int, Profile] = {}
    for pid in profile_ids or []:
        profile = db.get(Profile, pid)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile id {pid} not found",
            )
        resolved[profile.id] = profile
    for name in profile_names or []:
        profile, _ = get_or_create_profile(db, name)
        resolved[profile.id] = profile
    return list(resolved.values())


@router.get("", response_model=list[ProjectRead])
def list_projects(
    profile: str | None = Query(default=None, description="Filter by profile name"),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None, description="active|inactive|archived"),
    q: str | None = Query(default=None, description="Search title/description"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    query = db.query(Project).options(selectinload(Project.profiles))
    if profile:
        query = query.join(Project.profiles).filter(
            func.lower(Profile.name) == profile.strip().lower()
        )
    if category:
        query = query.filter(Project.category == category.strip().lower())
    if status:
        query = query.filter(Project.status == status.strip().lower())
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (Project.title.ilike(like)) | (Project.description.ilike(like))
        )
    return query.order_by(Project.updated_at.desc()).limit(limit).all()


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    project = Project(
        title=payload.title,
        description=payload.description,
        category=payload.category,
        status=payload.status,
        github_url=payload.github_url,
        live_url=payload.live_url,
        tech_stack=payload.tech_stack,
        result=payload.result,
        client_type=payload.client_type,
    )
    db.add(project)
    db.flush()
    profiles = _resolve_profiles(db, payload.profile_ids, payload.profile_names)
    if profiles is not None:
        project.profiles = profiles
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    project = (
        db.query(Project)
        .options(selectinload(Project.profiles))
        .filter(Project.id == project_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectRead)
@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    project = (
        db.query(Project)
        .options(selectinload(Project.profiles))
        .filter(Project.id == project_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    data = payload.model_dump(exclude_unset=True)
    profile_ids = data.pop("profile_ids", None)
    profile_names = data.pop("profile_names", None)
    for key, value in data.items():
        setattr(project, key, value)
    profiles = _resolve_profiles(db, profile_ids, profile_names)
    if profiles is not None:
        project.profiles = profiles
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return None


@router.post("/{project_id}/toggle-status", response_model=ProjectRead)
def toggle_status(
    project_id: int,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    project = (
        db.query(Project)
        .options(selectinload(Project.profiles))
        .filter(Project.id == project_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.status = "inactive" if project.status == "active" else "active"
    db.commit()
    db.refresh(project)
    return project
