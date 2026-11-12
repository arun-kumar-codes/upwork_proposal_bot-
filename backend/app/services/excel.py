"""Excel parsing, validation, and upsert shared by the API import and seed CLI."""

from dataclasses import dataclass, field
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import VALID_STATUSES, Profile, Project
from .profile_names import is_valid_profile_name

PROJECT_SHEET = "projects"
PROFILE_SHEET = "profiles"

PROJECT_COLUMNS = (
    "title",
    "description",
    "category",
    "status",
    "github_url",
    "live_url",
    "tech_stack",
    "result",
    "client_type",
    "profiles",
)
PROFILE_COLUMNS = ("name", "intro", "skills", "tone", "portfolio_url", "signature")


@dataclass
class RowError:
    sheet: str
    row: int
    errors: list[str]


@dataclass
class ParsedWorkbook:
    projects: list[dict] = field(default_factory=list)
    profiles: list[dict] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    has_projects_sheet: bool = False
    has_profiles_sheet: bool = False
    profiles_column_present: bool = False


def parse_list_cell(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = str(value).split(",")
    return [str(v).strip() for v in items if str(v).strip()]


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


MISSING_URL_VALUES = {"", "-", "\u2014", "n/a", "na", "null", "none", "not available"}


def clean_url(value: object) -> str | None:
    """URLs: '-', '', 'N/A' etc. mean missing, never a shared dedupe key."""
    text = clean_text(value)
    if text is None or text.lower() in MISSING_URL_VALUES:
        return None
    return text


def looks_like_profile_name(name: str) -> bool:
    """Reject documentation/legend sentences masquerading as profiles."""
    text = (name or "").strip()
    if not text or len(text) > 50 or len(text.split()) > 5:
        return False
    if text.endswith((".", ":", "\u2026")) or " = " in text or "http" in text.lower():
        return False
    return True


def norm_category(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _sheet_by_name(wb, name: str):
    for ws in wb.worksheets:
        if ws.title.strip().lower() == name:
            return ws
    return None


# Original-workbook header spellings -> canonical column names.
HEADER_ALIASES: dict[str, str] = {
    "project": "title",
    "profile": "profiles",
    "client": "client_type",
    "tags": "category",
    "git url": "github_url",
    "github": "github_url",
    "live link": "live_url",
    "live url": "live_url",
    "demo": "live_url",
    "website": "live_url",
    "notes": "result",
}


def _header_map(ws, *, profile_sheet: bool = False) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1))):
        if cell.value is None:
            continue
        header = str(cell.value).strip().lower()
        if profile_sheet and header in ("profile", "profile name"):
            header = "name"
        else:
            header = HEADER_ALIASES.get(header, header)
        # First spelling wins so an explicit canonical column beats an alias.
        mapping.setdefault(header, idx)
    return mapping


def _is_roster_sheet(ws) -> bool:
    """A 'Profile summary' doc sheet (legends/notes) is not a roster."""
    try:
        headers = {
            str(c.value).strip().lower()
            for c in next(ws.iter_rows(min_row=1, max_row=1))
            if c.value is not None
        }
    except StopIteration:
        return False
    known = {"name", "profile", "intro", "skills", "tone", "portfolio_url", "signature", "portfolio"}
    has_name = bool(headers & {"name", "profile"})
    return has_name and len(headers & known) >= 2


def parse_workbook(data: bytes) -> ParsedWorkbook:
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        parsed = ParsedWorkbook()
        parsed.errors.append(RowError(sheet="", row=0, errors=[f"Invalid .xlsx file: {exc}"]))
        return parsed

    parsed = ParsedWorkbook()
    ws = _sheet_by_name(wb, PROJECT_SHEET)
    if ws is not None:
        parsed.has_projects_sheet = True
        _parse_projects_sheet(ws, parsed)
    ws = _sheet_by_name(wb, PROFILE_SHEET)
    if ws is None:
        summary_ws = _sheet_by_name(wb, "profile summary")
        if summary_ws is not None and _is_roster_sheet(summary_ws):
            ws = summary_ws
    if ws is not None:
        parsed.has_profiles_sheet = True
        _parse_profiles_sheet(ws, parsed)
    if not parsed.has_projects_sheet and not parsed.has_profiles_sheet:
        parsed.errors.append(
            RowError(
                sheet="",
                row=0,
                errors=["Workbook has no 'projects' or 'profiles' sheet"],
            )
        )
    return parsed


def _parse_projects_sheet(ws, parsed: ParsedWorkbook) -> None:
    headers = _header_map(ws)
    parsed.profiles_column_present = "profiles" in headers
    for excel_row, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in row):
            continue

        def col(name: str) -> object:
            idx = headers.get(name)
            return row[idx] if idx is not None and idx < len(row) else None

        row_errors: list[str] = []
        title = clean_text(col("title"))
        if not title:
            row_errors.append("missing title")
        raw_status = col("status")
        status = "active"
        if raw_status is not None and str(raw_status).strip():
            status = str(raw_status).strip().lower()
            if status not in VALID_STATUSES:
                row_errors.append(
                    f"unknown status '{str(raw_status).strip()}' "
                    f"(expected one of: {', '.join(VALID_STATUSES)})"
                )
        if row_errors:
            parsed.errors.append(RowError(sheet=PROJECT_SHEET, row=excel_row, errors=row_errors))
            continue
        parsed.projects.append(
            {
                "row": excel_row,
                "title": title,
                "description": clean_text(col("description")),
                "category": norm_category(col("category")),
                "status": status,
                "github_url": clean_url(col("github_url")),
                "live_url": clean_url(col("live_url")),
                "tech_stack": parse_list_cell(col("tech_stack")),
                "result": clean_text(col("result")),
                "client_type": clean_text(col("client_type")),
                # Placeholder tokens ("Not named", "Unknown") are buckets for
                # unattributed rows, never profiles to create or link.
                "profiles": [
                    token
                    for token in parse_list_cell(col("profiles"))
                    if is_valid_profile_name(token)
                ],
            }
        )


def _parse_profiles_sheet(ws, parsed: ParsedWorkbook) -> None:
    headers = _header_map(ws, profile_sheet=True)
    for excel_row, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in row):
            continue

        def col(name: str) -> object:
            idx = headers.get(name)
            return row[idx] if idx is not None and idx < len(row) else None

        name = clean_text(col("name"))
        if not name:
            parsed.errors.append(
                RowError(sheet=PROFILE_SHEET, row=excel_row, errors=["missing name"])
            )
            continue
        if not looks_like_profile_name(name) or not is_valid_profile_name(name):
            continue  # documentation/legend row or placeholder, not a person
        parsed.profiles.append(
            {
                "row": excel_row,
                "name": name,
                "intro": clean_text(col("intro")),
                "skills": parse_list_cell(col("skills")),
                "tone": clean_text(col("tone")),
                "portfolio_url": clean_text(col("portfolio_url")),
                "signature": clean_text(col("signature")),
            }
        )


def get_or_create_profile(db: Session, name: str) -> tuple[Profile, bool]:
    existing = (
        db.query(Profile).filter(func.lower(Profile.name) == name.lower()).first()
    )
    if existing:
        return existing, False
    profile = Profile(name=name)
    db.add(profile)
    db.flush()
    return profile, True


def find_project(db: Session, github_url: str | None, title: str) -> Project | None:
    # Only a real URL identifies a project; "-" / missing must fall through
    # to the title match so distinct titles never collapse onto one row.
    if github_url and github_url.lower().startswith(("http://", "https://")):
        match = db.query(Project).filter(Project.github_url == github_url).first()
        if match:
            return match
    return db.query(Project).filter(func.lower(Project.title) == title.lower()).first()


def missing_live_url_count(parsed: ParsedWorkbook) -> int:
    """Valid project rows with no live demo URL (proposals need live links)."""
    return sum(1 for item in parsed.projects if not item.get("live_url"))


def upsert_all(db: Session, parsed: ParsedWorkbook) -> dict:
    profiles_created = 0
    profiles_updated = 0
    for item in parsed.profiles:
        profile, created = get_or_create_profile(db, item["name"])
        if created:
            profiles_created += 1
        else:
            profiles_updated += 1
        for key in ("intro", "skills", "tone", "portfolio_url", "signature"):
            setattr(profile, key, item[key])

    projects_created = 0
    projects_updated = 0
    for item in parsed.projects:
        project = find_project(db, item["github_url"], item["title"])
        if project is None:
            project = Project(title=item["title"])
            db.add(project)
            db.flush()
            projects_created += 1
        else:
            projects_updated += 1
        for key in (
            "title",
            "description",
            "category",
            "status",
            "github_url",
            "live_url",
            "tech_stack",
            "result",
            "client_type",
        ):
            setattr(project, key, item[key])
        # Only touch links when the sheet carries a non-empty profiles cell,
        # so re-imports never wipe links managed in the dashboard.
        if parsed.profiles_column_present and item["profiles"]:
            project.profiles = [
                get_or_create_profile(db, name)[0] for name in item["profiles"]
            ]

    db.commit()
    return {
        "missing_live_url": missing_live_url_count(parsed),
        "projects_created": projects_created,
        "projects_updated": projects_updated,
        "profiles_created": profiles_created,
        "profiles_updated": profiles_updated,
        "project_rows": len(parsed.projects),
        "profile_rows": len(parsed.profiles),
        "error_rows": len(parsed.errors),
    }
