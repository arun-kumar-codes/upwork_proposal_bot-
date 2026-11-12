"""Project Hub API: projects + profiles store for the proposal bot."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import auth, github, import_excel, meta, playground, profiles, projects

app = FastAPI(title="Project Hub API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(profiles.router, prefix="/api")
app.include_router(import_excel.router, prefix="/api")
app.include_router(playground.router, prefix="/api")
app.include_router(github.router, prefix="/api")
app.include_router(meta.router, prefix="/api")


@app.get("/")
def root():
    return {"ok": True, "service": "project-hub", "docs": "/docs"}


@app.get("/health")
def health():
    return {"ok": True}
