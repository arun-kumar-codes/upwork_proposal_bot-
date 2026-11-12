"""SQLAlchemy models: Project, Profile, and their many-to-many link."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

VALID_STATUSES = ("active", "inactive", "archived")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


project_profiles = Table(
    "project_profiles",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("profile_id", ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    live_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tech_stack: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    profiles: Mapped[list["Profile"]] = relationship(
        secondary=project_profiles, back_populates="projects"
    )


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    intro: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tone: Mapped[str | None] = mapped_column(String(200), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    projects: Mapped[list[Project]] = relationship(
        secondary=project_profiles, back_populates="profiles"
    )


class PlaygroundRun(Base):
    """Saved Test Playground run: input, selected projects, reply, time."""

    __tablename__ = "playground_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_name: Mapped[str] = mapped_column(String(200), nullable=False)
    client_message: Mapped[str] = mapped_column(Text, nullable=False)
    category_override: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detected_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_source: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    selected: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reply: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="simulated")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
