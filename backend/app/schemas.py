"""Pydantic schemas with the same normalization as the Excel import."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

Status = Literal["active", "inactive", "archived"]


def _clean_str(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return value


def _clean_status(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().lower()
        return value if value else "active"
    return value


def _clean_category(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _clean_str_list(value: object) -> object:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    if isinstance(value, (list, tuple)):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return value


class ProfileSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str = ""
    status: str = "active"
    github_url: str | None = None
    live_url: str | None = None
    tech_stack: list[str] = []


class ProjectBase(BaseModel):
    title: str
    description: str | None = None
    category: str = ""
    status: Status = "active"
    github_url: str | None = None
    live_url: str | None = None
    tech_stack: list[str] = []
    result: str | None = None
    client_type: str | None = None

    _norm_title = field_validator("title", mode="before")(_clean_str)
    _norm_status = field_validator("status", mode="before")(_clean_status)
    _norm_category = field_validator("category", mode="before")(_clean_category)
    _norm_stack = field_validator("tech_stack", mode="before")(_clean_str_list)

    @field_validator(
        "description", "github_url", "live_url", "result", "client_type", mode="before"
    )
    @classmethod
    def _strip_optional(cls, value: object) -> object:
        return _clean_str(value)


class ProjectCreate(ProjectBase):
    profile_ids: list[int] = []
    profile_names: list[str] = []

    _norm_names = field_validator("profile_names", mode="before")(_clean_str_list)


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    status: Status | None = None
    github_url: str | None = None
    live_url: str | None = None
    tech_stack: list[str] | None = None
    result: str | None = None
    client_type: str | None = None
    profile_ids: list[int] | None = None
    profile_names: list[str] | None = None

    _norm_title = field_validator("title", mode="before")(_clean_str)
    _norm_status = field_validator("status", mode="before")(_clean_status)
    _norm_category = field_validator("category", mode="before")(_clean_category)
    _norm_stack = field_validator("tech_stack", mode="before")(_clean_str_list)
    _norm_names = field_validator("profile_names", mode="before")(_clean_str_list)

    @field_validator(
        "description", "github_url", "live_url", "result", "client_type", mode="before"
    )
    @classmethod
    def _strip_optional(cls, value: object) -> object:
        return _clean_str(value)


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    profiles: list[ProfileSummary] = []


class ProfileBase(BaseModel):
    name: str
    intro: str | None = None
    skills: list[str] = []
    tone: str | None = None
    portfolio_url: str | None = None
    signature: str | None = None

    _norm_name = field_validator("name", mode="before")(_clean_str)
    _norm_skills = field_validator("skills", mode="before")(_clean_str_list)

    @field_validator("intro", "tone", "portfolio_url", "signature", mode="before")
    @classmethod
    def _strip_optional(cls, value: object) -> object:
        return _clean_str(value)


class ProfileCreate(ProfileBase):
    project_ids: list[int] = []


class ProfileUpdate(BaseModel):
    name: str | None = None
    intro: str | None = None
    skills: list[str] | None = None
    tone: str | None = None
    portfolio_url: str | None = None
    signature: str | None = None
    project_ids: list[int] | None = None

    _norm_name = field_validator("name", mode="before")(_clean_str)
    _norm_skills = field_validator("skills", mode="before")(_clean_str_list)

    @field_validator("intro", "tone", "portfolio_url", "signature", mode="before")
    @classmethod
    def _strip_optional(cls, value: object) -> object:
        return _clean_str(value)


class ProfileRead(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    projects: list[ProjectSummary] = []


class ProfileWithProjects(ProfileRead):
    """Profile detail for the bot: all linked projects plus the active subset."""

    active_projects: list[ProjectSummary] = []


class PlaygroundRunRequest(BaseModel):
    profile: str
    client_message: str
    category_override: str | None = None
    mode: Literal["simulated", "real_bot"] = "simulated"
    limit: int = 3

    @field_validator("profile", "client_message", mode="before")
    @classmethod
    def _strip_required(cls, value: object) -> object:
        return _clean_str(value)

    _norm_override = field_validator("category_override", mode="before")(
        lambda v: _clean_category(v) or None
    )

    @field_validator("limit", mode="before")
    @classmethod
    def _clamp_limit(cls, value: object) -> object:
        try:
            return max(1, min(10, int(value)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return value


class SelectedProject(BaseModel):
    project: ProjectSummary
    reason: str


class PlaygroundRunResult(BaseModel):
    run_id: int
    detected_category: str | None = None
    category_source: str = "none"
    selected: list[SelectedProject] = []
    reply: str = ""
    mode: str = "simulated"
    created_at: datetime


class PlaygroundHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_name: str
    client_message: str
    category_override: str | None = None
    detected_category: str | None = None
    category_source: str = "none"
    selected: list = []
    reply: str = ""
    error: str | None = None
    mode: str = "simulated"
    created_at: datetime
