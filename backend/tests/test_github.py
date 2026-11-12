"""GitHub prefill: URL parsing (unit) + endpoint validation (no network)."""

from app.services.github import parse_repo_url


def test_parse_repo_url():
    assert parse_repo_url("https://github.com/owner/repo") == ("owner", "repo")
    assert parse_repo_url("https://github.com/owner/repo.git") == ("owner", "repo")
    assert parse_repo_url("https://github.com/owner/repo/tree/main") == ("owner", "repo")
    assert parse_repo_url("  owner/repo  ") == ("owner", "repo")
    assert parse_repo_url("not a repo") is None
    assert parse_repo_url("") is None
    assert parse_repo_url("https://example.com/owner/repo") is None


def test_prefill_rejects_unparseable_url(client):
    resp = client.get("/api/github/prefill", params={"url": "not a repo"})
    assert resp.status_code == 400
    assert "GitHub" in resp.json()["detail"]


def test_prefill_requires_url(client):
    resp = client.get("/api/github/prefill")
    assert resp.status_code == 422
