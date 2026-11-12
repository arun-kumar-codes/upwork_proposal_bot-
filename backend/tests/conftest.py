"""Shared test fixtures: isolated SQLite DB + API-key authed TestClient."""

import os

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test-should-be-overridden.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture()
def client(db_path):
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.headers["X-API-Key"] = "test-key"
        yield c
    app.dependency_overrides.clear()
