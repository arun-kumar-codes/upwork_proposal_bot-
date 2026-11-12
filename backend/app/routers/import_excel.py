"""Excel import: preview + validation report, or upsert save."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_api_key
from ..services.excel import missing_live_url_count, parse_workbook, upsert_all

router = APIRouter(prefix="/import", tags=["import"])

MAX_BYTES = 10 * 1024 * 1024


@router.post("/excel")
async def import_excel(
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False, description="Preview without saving"),
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Upload an .xlsx file")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    parsed = parse_workbook(data)
    errors = [
        {"sheet": e.sheet, "row": e.row, "errors": e.errors} for e in parsed.errors
    ]
    if dry_run:
        return {
            "dry_run": True,
            "has_projects_sheet": parsed.has_projects_sheet,
            "has_profiles_sheet": parsed.has_profiles_sheet,
            "projects": parsed.projects,
            "profiles": parsed.profiles,
            "errors": errors,
            "summary": {
                "project_rows": len(parsed.projects),
                "profile_rows": len(parsed.profiles),
                "error_rows": len(errors),
                "missing_live_url": missing_live_url_count(parsed),
            },
        }
    summary = upsert_all(db, parsed)
    return {"dry_run": False, "summary": summary, "errors": errors}

@router.post("/preview")
async def import_preview(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    """Alias of POST /excel?dry_run=true (older frontends call this path)."""
    return await import_excel(file=file, dry_run=True, db=db, _auth=_auth)
