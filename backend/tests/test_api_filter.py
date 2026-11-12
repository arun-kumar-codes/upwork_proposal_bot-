"""API filter endpoint: profile/category/status/limit + toggle + profile lookup."""

from fastapi.testclient import TestClient


def _seed(client: TestClient):
    web = client.post("/api/profiles", json={"name": "Web Dev"}).json()
    data = client.post("/api/profiles", json={"name": "Data AI"}).json()

    def make(title, **kw):
        payload = {"title": title, "category": "web", "status": "active", **kw}
        assert client.post("/api/projects", json=payload).status_code == 201, payload

    make("Shop Site", profile_names=["Web Dev"], tech_stack=["nextjs"])
    make("Blog Engine", category="Web", profile_names=["web dev"])  # case-insensitive
    make("Churn Model", category="ml", status="active", profile_names=["Data AI"])
    make("Old Landing", status="inactive", profile_names=["Web Dev"])
    make("Retired App", status="archived", category="ml", profile_names=["Data AI"])
    return web, data


def test_filter_by_profile_category_status_and_limit(client: TestClient):
    _seed(client)
    resp = client.get(
        "/api/projects",
        params={"profile": "Web Dev", "category": "web", "status": "active", "limit": 3},
    )
    assert resp.status_code == 200
    titles = sorted(p["title"] for p in resp.json())
    assert titles == ["Blog Engine", "Shop Site"]


def test_limit_is_respected(client: TestClient):
    _seed(client)
    resp = client.get("/api/projects", params={"status": "active", "limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_profile_lookup_returns_active_projects(client: TestClient):
    _seed(client)
    resp = client.get("/api/profiles/Web Dev")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Web Dev"
    assert sorted(p["title"] for p in body["active_projects"]) == [
        "Blog Engine",
        "Shop Site",
    ]
    assert len(body["projects"]) == 3  # includes the inactive one


def test_toggle_status_flips_active_inactive(client: TestClient):
    _seed(client)
    project = client.get("/api/projects", params={"q": "Shop Site"}).json()[0]
    assert project["status"] == "active"
    toggled = client.post(f"/api/projects/{project['id']}/toggle-status").json()
    assert toggled["status"] == "inactive"
    toggled = client.post(f"/api/projects/{project['id']}/toggle-status").json()
    assert toggled["status"] == "active"


def test_missing_api_key_is_rejected(client: TestClient):
    del client.headers["X-API-Key"]
    resp = client.get("/api/projects")
    assert resp.status_code == 401


def test_crud_roundtrip(client: TestClient):
    created = client.post(
        "/api/projects",
        json={"title": "  Temp  ", "category": " WEB ", "tech_stack": "a, b "},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Temp"  # trimmed
    assert body["category"] == "web"  # lowercased
    assert body["tech_stack"] == ["a", "b"]  # comma string -> list

    pid = body["id"]
    assert client.get(f"/api/projects/{pid}").status_code == 200
    updated = client.put(f"/api/projects/{pid}", json={"status": "Archived"}).json()
    assert updated["status"] == "archived"
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
