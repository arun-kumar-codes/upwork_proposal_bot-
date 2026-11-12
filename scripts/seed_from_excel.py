#!/usr/bin/env python3
"""Seed the database from an .xlsx file (sheets: projects, profiles).

Usage:
    source .venv/bin/activate
    python scripts/seed_from_excel.py data.xlsx [--dry-run]

DATABASE_URL is read from the environment (or repo-root .env).
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Project  # noqa: E402,F401
from app.services.excel import parse_workbook, upsert_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Project Hub from Excel.")
    parser.add_argument("xlsx", help="Path to the .xlsx file")
    parser.add_argument("--dry-run", action="store_true", help="Validate only")
    args = parser.parse_args()

    path = Path(args.xlsx)
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    parsed = parse_workbook(path.read_bytes())
    print(
        f"Sheets: projects={'yes' if parsed.has_projects_sheet else 'no'}, "
        f"profiles={'yes' if parsed.has_profiles_sheet else 'no'}"
    )
    print(f"Valid rows: {len(parsed.projects)} projects, {len(parsed.profiles)} profiles")
    for err in parsed.errors:
        print(f"  [{err.sheet} row {err.row}] {'; '.join(err.errors)}")
    if args.dry_run:
        print("Dry run: nothing saved.")
        return 0 if not parsed.errors else 2

    Base.metadata.create_all(bind=engine)  # ensure tables exist for fresh SQLite dev DBs
    db = SessionLocal()
    try:
        summary = upsert_all(db, parsed)
    finally:
        db.close()
    print(
        "Saved: "
        f"{summary['projects_created']} projects created, "
        f"{summary['projects_updated']} updated, "
        f"{summary['profiles_created']} profiles created, "
        f"{summary['profiles_updated']} updated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
