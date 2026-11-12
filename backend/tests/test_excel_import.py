"""Excel import: preview/validation, save, normalization, no-duplicate re-import."""

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook


def _workbook_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "projects"
    ws.append(
        [
            "title", "description", "category", "status", "github_url", "live_url",
            "tech_stack", "result", "client_type", "profiles",
        ]
    )
    ws.append(
        [
            "Shop Site", "Store", " Web ", "Active",
            "https://github.com/me/shop", "", "nextjs, tailwind",
            "+20% sales", "startup", "Web Dev",
        ]
    )
    ws.append(["", "no title", "web", "active", "", "", "", "", "", ""])  # error
    ws.append(["Weird", "bad status", "web", "pending", "", "", "", "", "", ""])  # error
    ws2 = wb.create_sheet("profiles")
    ws2.append(["name", "intro", "skills", "tone", "portfolio_url", "signature"])
    ws2.append(["Web Dev", "I build", "nextjs, python", "pro", "", "Thanks"])
    ws2.append(["", "missing name", "", "", "", ""])  # error
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client: TestClient, dry_run: bool):
    return client.post(
        "/api/import/excel",
        params={"dry_run": dry_run},
        files={"file": ("seed.xlsx", _workbook_bytes(), "application/vnd.ms-excel")},
    )


def test_dry_run_reports_errors_without_saving(client: TestClient):
    resp = _upload(client, dry_run=True)
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["summary"] == {"project_rows": 1, "profile_rows": 1, "error_rows": 3, "missing_live_url": 1}
    flat = " ".join(" ".join(e["errors"]) for e in body["errors"])
    assert "missing title" in flat
    assert "unknown status" in flat
    assert "missing name" in flat
    # Nothing persisted.
    assert client.get("/api/projects").json() == []
    assert client.get("/api/profiles").json() == []


def test_save_then_reimport_never_duplicates(client: TestClient):
    first = _upload(client, dry_run=False)
    assert first.status_code == 200
    assert first.json()["summary"]["projects_created"] == 1
    assert first.json()["summary"]["profiles_created"] == 1

    projects = client.get("/api/projects").json()
    assert len(projects) == 1
    assert projects[0]["tech_stack"] == ["nextjs", "tailwind"]
    assert projects[0]["category"] == "web"
    assert projects[0]["status"] == "active"
    assert [p["name"] for p in projects[0]["profiles"]] == ["Web Dev"]

    second = _upload(client, dry_run=False)
    assert second.status_code == 200
    summary = second.json()["summary"]
    assert summary["projects_created"] == 0
    assert summary["projects_updated"] == 1
    assert summary["profiles_created"] == 0
    assert len(client.get("/api/projects").json()) == 1


def test_rejects_non_excel(client: TestClient):
    resp = client.post(
        "/api/import/excel",
        files={"file": ("seed.txt", b"nope", "text/plain")},
    )
    assert resp.status_code == 400


def _original_workbook_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Projects"
    ws.append(
        ["Profile", "Project", "Client", "Status", "AI", "Full stack", "Automation",
         "Tags", "Description", "Git URL", "Live link", "Notes"]
    )
    ws.append(
        ["Atul", "Portfolio Site", "Internal", "Active", "", "", "",
         "AI + Full Stack", "My site", "https://github.com/demo/portfolio",
         "https://portfolio.example.com", "Shipped v2"]
    )
    ws.append(
        ["", "No Live Tool", "", "inactive", "", "", "", "automation",
         "Internal tool", "", "", ""]
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_original_headers_project_and_live_link(client: TestClient):
    resp = client.post(
        "/api/import/excel",
        params={"dry_run": False},
        files={"file": ("All-Projects.xlsx", _original_workbook_bytes(), "application/vnd.ms-excel")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["summary"]["missing_live_url"] == 1
    projects = {p["title"]: p for p in client.get("/api/projects?limit=100").json()}
    site = projects["Portfolio Site"]
    assert site["live_url"] == "https://portfolio.example.com"  # Live link -> live_url
    assert site["github_url"] == "https://github.com/demo/portfolio"  # Git URL -> github_url
    assert site["category"] == "ai + full stack"  # Tags -> category
    assert site["client_type"] == "Internal"  # Client -> client_type
    assert site["result"] == "Shipped v2"  # Notes -> result
    assert [p["name"] for p in site["profiles"]] == ["Atul"]  # Profile -> profiles
    assert projects["No Live Tool"]["status"] == "inactive"


def _dash_workbook_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Projects"
    ws.append(["Profile", "Project", "Status", "Tags", "Git URL", "Live link"])
    ws.append(["Atul", "Alpha Tool", "active", "web", "-", "-"])
    ws.append(["Atul", "Beta Tool", "active", "web", "-", "https://beta.example.com"])
    ws.append(["", "Gamma Tool", "inactive", "ml", "", ""])
    doc = wb.create_sheet("Profile summary")
    doc.append(["How Status was decided"])
    doc.append(["Filter Status column for Active or Inactive"])
    doc.append(["Active = In-Progress, live ops still open"])
    ws2 = wb.create_sheet("profiles")
    ws2.append(["name", "intro"])
    ws2.append(["Atul", "Builder"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_placeholder_profile_tokens_never_become_profiles(client: TestClient):
    """'Not named'/'Unknown' tokens are buckets, not freelancers: never imported as profiles."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Projects"
    ws.append(["Profile", "Project", "Status", "Tags", "Git URL", "Live link"])
    ws.append(["Not named", "Orphan Tool", "active", "web", "", ""])
    ws.append(["Atul", "Atul Tool", "active", "web", "", "https://atul.example.com"])
    ws2 = wb.create_sheet("profiles")
    ws2.append(["name", "intro"])
    ws2.append(["Unknown", "should be skipped"])
    buf = BytesIO()
    wb.save(buf)
    resp = client.post(
        "/api/import/excel",
        files={"file": ("All-Projects.xlsx", buf.getvalue(), "application/vnd.ms-excel")},
    )
    assert resp.status_code == 200, resp.text
    names = [p["name"] for p in client.get("/api/profiles").json()]
    assert names == ["Atul"]
    projects = {p["title"]: p for p in client.get("/api/projects?limit=100").json()}
    assert projects["Orphan Tool"]["profiles"] == []  # unattributed, not bucketed
    assert [p["name"] for p in projects["Atul Tool"]["profiles"]] == ["Atul"]


def test_dash_urls_do_not_collapse_and_preview_route(client: TestClient):
    data = _dash_workbook_bytes()
    preview = client.post(
        "/api/import/preview",
        files={"file": ("All-Projects.xlsx", data, "application/vnd.ms-excel")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["dry_run"] is True
    assert preview.json()["summary"]["missing_live_url"] == 2  # Alpha "-" + Gamma ""
    assert client.get("/api/projects").json() == []  # preview saved nothing

    saved = client.post(
        "/api/import/excel",
        files={"file": ("All-Projects.xlsx", data, "application/vnd.ms-excel")},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["summary"]["missing_live_url"] == 2
    projects = {p["title"]: p for p in client.get("/api/projects?limit=100").json()}
    assert set(projects) == {"Alpha Tool", "Beta Tool", "Gamma Tool"}  # no collapse on "-"
    assert projects["Alpha Tool"]["github_url"] is None
    assert projects["Alpha Tool"]["live_url"] is None
    assert projects["Beta Tool"]["live_url"] == "https://beta.example.com"
    names = [p["name"] for p in client.get("/api/profiles").json()]
    assert names == ["Atul"]  # Profile summary legends never became profiles
