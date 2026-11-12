#!/usr/bin/env python3
"""Normalize profile name aliases. Dry-run by default; --apply writes.

Usage:
    python scripts/normalize_profiles.py [--aliases scripts/profile_aliases.json]
    python scripts/normalize_profiles.py --apply   # backs up the SQLite DB first

For each profile whose name matches an alias, the plan is: rename it to the
canonical name, or merge it (re-link its projects, then delete it) when the
canonical profile already exists. Canonical names and names absent from the
alias map are reported as unresolved and never touched. Postgres DATABASE_URLs
are refused on --apply (take a pg_dump backup manually first).
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

# Anchor a relative SQLite DATABASE_URL at backend/ (where the Hub runs),
# so this script and the Hub open the same file regardless of caller cwd.
import os  # noqa: E402

_env_url = os.environ.get("DATABASE_URL", "")
if not _env_url:
    for _line in (REPO_ROOT / ".env").read_text().splitlines() if (REPO_ROOT / ".env").exists() else []:
        if _line.strip().startswith("DATABASE_URL="):
            _env_url = _line.split("=", 1)[1].strip()
            break
if _env_url.startswith("sqlite:///./"):
    _candidate = REPO_ROOT / "backend" / _env_url[len("sqlite:///./"):]
    if _candidate.exists():
        os.environ["DATABASE_URL"] = f"sqlite:///{_candidate}"

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Profile  # noqa: E402


def load_aliases(path: Path) -> dict[str, str]:
    """alias (lower) -> canonical name."""
    raw = json.loads(path.read_text())
    mapping: dict[str, str] = {}
    for canonical, aliases in raw.items():
        if canonical.startswith("_"):
            continue
        mapping[canonical.lower()] = canonical
        for alias in aliases or []:
            mapping[str(alias).lower()] = canonical
    return mapping


def plan_actions(profiles: list, alias_to_canonical: dict[str, str]) -> tuple[list[dict], list[str]]:
    """Pure planner: (actions, unresolved names). No DB access, unit-testable."""
    by_lower = {p.name.lower(): p for p in profiles}
    actions: list[dict] = []
    unresolved: list[str] = []
    for profile in profiles:
        canonical = alias_to_canonical.get(profile.name.lower())
        if canonical is None:
            unresolved.append(profile.name)
        elif canonical == profile.name:
            continue  # already canonical
        elif canonical.lower() in by_lower:
            actions.append({"action": "merge", "from": profile.name, "into": canonical})
        else:
            actions.append({"action": "rename", "from": profile.name, "into": canonical})
    return actions, unresolved


def sqlite_db_path(url: str) -> Path | None:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix):]
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / "backend" / path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize profile aliases (dry-run default).")
    parser.add_argument("--aliases", default=str(REPO_ROOT / "scripts" / "profile_aliases.json"))
    parser.add_argument("--apply", action="store_true", help="Write changes (SQLite backup first)")
    args = parser.parse_args()

    alias_path = Path(args.aliases)
    if not alias_path.exists():
        print(f"Alias file not found: {alias_path}")
        return 1
    alias_to_canonical = load_aliases(alias_path)

    db = SessionLocal()
    try:
        profiles = db.query(Profile).all()
        for p in profiles:
            _ = len(p.projects)  # warm links for the planner/merge counts
        actions, unresolved = plan_actions(profiles, alias_to_canonical)

        print(f"Profiles: {len(profiles)} total")
        for action in actions:
            verb = "merge into" if action["action"] == "merge" else "rename to"
            print(f"  PLAN {action['action']}: '{action['from']}' {verb} '{action['into']}'")
        if not actions:
            print("  No renames/merges needed.")
        if unresolved:
            print("Unresolved (not in alias map, left untouched): " + ", ".join(sorted(unresolved)))
        else:
            print("Unresolved: none")

        if not args.apply:
            print("Dry run: nothing saved. Re-run with --apply to write.")
            return 0
        if not actions:
            print("Nothing to apply.")
            return 0

        db_path = sqlite_db_path(settings.DATABASE_URL)
        if db_path is None or not db_path.exists():
            print(f"--apply needs a SQLite file DATABASE_URL (got: {settings.DATABASE_URL}). Aborting.")
            return 1
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = db_path.with_name(f"{db_path.name}.bak-{stamp}")
        shutil.copy2(db_path, backup)
        print(f"Backup: {backup}")

        by_lower = {p.name.lower(): p for p in profiles}
        for action in actions:
            source = by_lower[action["from"].lower()]
            if action["action"] == "rename":
                source.name = action["into"]
                by_lower[action["into"].lower()] = source
            else:
                target = by_lower[action["into"].lower()]
                for project in list(source.projects):
                    if project not in target.projects:
                        target.projects.append(project)
                source.projects = []
                db.delete(source)
        db.commit()
        print(f"Applied {len(actions)} action(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
