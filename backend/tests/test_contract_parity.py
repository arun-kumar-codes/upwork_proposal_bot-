"""Hub Real-Bot contract parity: categories, meta, status, generate, history."""

import asyncio
from io import BytesIO

import httpx
from openpyxl import Workbook


def _seed(client):
    client.post("/api/profiles", json={"name": "Web Dev", "skills": ["nextjs"]})
    client.post("/api/profiles", json={"name": "Data AI"})
    for payload in [
        {"title": "Shop API", "category": "web", "status": "active", "profile_names": ["Web Dev"],
         "github_url": "https://github.com/demo/shop", "live_url": "https://shop.example.com"},
        {"title": "Blog Theme", "category": "Web", "status": "active", "profile_names": ["Web Dev"]},
        {"title": "ML Pipeline", "category": "ml", "status": "active", "profile_names": ["Data AI"]},
        {"title": "Old Site", "category": "web", "status": "inactive", "profile_names": ["Web Dev"]},
    ]:
        assert client.post("/api/projects", json=payload).status_code == 201


def test_categories_distinct_sorted(client):
    _seed(client)
    assert client.get("/api/categories").json() == ["ml", "web"]
    assert client.get("/api/projects").status_code == 200  # auth fixture sanity


def test_categories_empty_initially(client):
    assert client.get("/api/categories").json() == []


def test_meta_profiles_counts(client):
    _seed(client)
    data = client.get("/api/meta/profiles").json()
    by_name = {p["name"]: p for p in data}
    assert by_name["Web Dev"]["project_count"] == 3
    assert by_name["Web Dev"]["active_project_count"] == 2
    assert by_name["Data AI"]["active_project_count"] == 1
    assert "projects" not in by_name["Web Dev"]  # lightweight meta, not full detail


def test_playground_status_shape(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "BOT_URL", "http://bot:9000")
    monkeypatch.setattr(settings, "BOT_API_KEY", None)
    monkeypatch.setattr(settings, "GITHUB_TOKEN", None)
    data = client.get("/api/playground/status").json()
    assert data["llm_configured"] is False
    assert data["bot_configured"] is False  # URL without key is not configured
    assert data["github_configured"] is False
    assert data["llm_model"] == settings.LLM_MODEL

    monkeypatch.setattr(settings, "BOT_API_KEY", "test-bot-key")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai")
    assert client.get("/api/playground/status").json()["bot_configured"] is True
    assert client.get("/api/playground/status").json()["llm_configured"] is True


def test_playground_status_llm_alias_env(client, monkeypatch):
    """LLM_API_KEY / LLM_BASE_URL (OpenAI-compatible naming) also configure the LLM."""
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-llm-key")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://llm.example.com/v1/")
    data = client.get("/api/playground/status").json()
    assert data["llm_configured"] is True
    assert settings.openai_chat_url == "https://llm.example.com/v1/chat/completions"


def test_generate_alias_matches_run(client, monkeypatch):
    import app.routers.playground as pg

    async def _fake_reply(**kwargs):
        return "ALIAS REPLY"

    _seed(client)
    monkeypatch.setattr(pg, "generate_reply", _fake_reply)
    body = {"profile": "Web Dev", "client_message": "Need a web app", "mode": "simulated"}
    via_run = client.post("/api/playground/run", json=body)
    via_gen = client.post("/api/playground/generate", json=body)
    assert via_run.status_code == 200 and via_gen.status_code == 200
    assert via_gen.json()["reply"] == "ALIAS REPLY"
    assert via_gen.json()["run_id"] != via_run.json()["run_id"]  # each call persists


def test_history_by_id_and_error_persisted(client, monkeypatch):
    import app.services.playground as svc

    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(svc.settings, "LLM_API_KEY", None)
    _seed(client)
    ok = client.post(
        "/api/playground/generate",
        json={"profile": "Web Dev", "client_message": "Need a web app for our shop", "mode": "simulated"},
    )
    # Simulated without a key fails (400) but must persist with error set.
    # (The message must match a seeded project: with the relevance floor,
    # an unmatched message takes the honest proof-free path instead.)
    assert ok.status_code == 400
    history = client.get("/api/playground/history").json()
    assert len(history) == 1
    assert history[0]["error"] and "OPENAI_API_KEY" in history[0]["error"]
    assert history[0]["reply"] == ""

    fetched = client.get(f"/api/playground/history/{history[0]['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == history[0]["id"]
    assert client.get("/api/playground/history/99999").status_code == 404


def test_brief_is_live_url_only():
    from app.models import Project
    from app.services.playground import _project_brief

    brief = _project_brief(
        Project(title="Shop", github_url="https://github.com/demo/shop",
                live_url="https://shop.example.com", tech_stack=[], description=None)
    )
    assert "shop.example.com" in brief
    assert "github.com" not in brief
    no_live = _project_brief(
        Project(title="Secret", github_url="https://github.com/demo/secret",
                live_url=None, tech_stack=[])
    )
    assert "github.com" not in no_live and "no live demo link" in no_live


def test_simulated_prompt_has_no_github_url(client, monkeypatch):
    import app.services.playground as svc

    captured = {}

    # No skill claim: this profile has no verified skills in Hub data.
    valid_reply = (
        "hey there\n"
        "I am Web Dev a web dev\n"
        "recently I worked on Shop https://shop.example.com\n"
        "it is live right now and real users use it daily.\n"
        "Please let me know when we can proceed further.\n"
        "Best regards\n"
        "Web Dev"
    )

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": valid_reply}}]}

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured["json"] = json
            return _Resp()

    _seed(client)
    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)
    profile = client.get("/api/profiles/Web Dev").json()
    assert profile["name"] == "Web Dev"
    # Call the service directly with ORM objects fetched via the API-seeded DB is
    # awkward across sessions; assert on the brief + prompt rule via unit path:
    from app.models import Profile, Project

    reply = asyncio.run(
        svc.generate_reply(
            profile=Profile(name="Web Dev", skills=[], intro="hi"),
            projects=[Project(title="Shop", github_url="https://github.com/demo/shop",
                              live_url="https://shop.example.com", tech_stack=[])],
            client_message="Need a store",
        )
    )
    assert reply == valid_reply
    prompt_text = str(captured["json"])
    assert "github.com/demo/shop" not in prompt_text
    assert "shop.example.com" in prompt_text
    assert "LIVE demo" in prompt_text


def test_select_projects_falls_back_when_category_has_no_match():
    from app.models import Project
    from app.services.playground import select_projects

    projects = [
        Project(title="Old Web", category="web", live_url=None),
        Project(title="Live One", category="ai", live_url="https://live.example.com"),
    ]
    # Compound Hub categories share tokens: "ai" is a related match here.
    picked = select_projects(projects, "ai + full stack + automation", 3)
    assert [p.title for p, _ in picked] == ["Live One"]
    assert "related category" in picked[0][1]
    # A truly unrelated category passes nothing through the relevance
    # floor: no project has a relevance reason, so selection is empty and
    # the proposal takes the honest proof-free path.
    picked = select_projects(projects, "shopify", 3)
    assert picked == []


def test_simulated_corporate_llm_output_falls_back_to_contract(client, monkeypatch):
    """Simulated must ship the Real Bot contract even when the LLM writes a cover letter."""
    import app.services.playground as svc

    corporate = (
        "Hi Aparna, Thank you for reaching out! I would love to help you navigate "
        "and enhance your platform with a seamless experience. Looking forward "
        "to connecting. Best, Aayush"
    )

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": corporate}}]}

        def raise_for_status(self):
            pass

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            return _Resp()

    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)
    from app.models import Profile, Project

    reply = asyncio.run(
        svc.generate_reply(
            profile=Profile(name="Aayush", skills=["React"], intro="hi"),
            projects=[
                Project(
                    title="Lovable Store Builder",
                    category="web",
                    github_url="https://github.com/demo/lovable",
                    live_url="https://lovable.example.com",
                    description="store builder made with React",
                    tech_stack=["react"],
                )
            ],
            client_message="Hi I am Aparna we need a Lovable style web app for our store",
        )
    )
    assert "hey" in reply.lower()
    assert "I am Aayush" in reply
    assert "recently" in reply
    assert "https://lovable.example.com" in reply
    assert (
        "please review my portfolio: "
        "http://116.202.210.102:3700/portfolio/6943d95d20eafc5a71c0f96b"
    ) in reply
    assert "Thank you for reaching out" not in reply
    assert "Looking forward to connecting" not in reply
    assert "github.com" not in reply
    assert "," not in reply


def _xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "projects"
    ws.append(["title", "category", "status", "github_url", "live_url", "tech_stack", "profiles"])
    ws.append(["Live One", "web", "active", "", "https://live.example.com", "", "Web Dev"])
    ws.append(["No Live", "web", "active", "https://github.com/demo/nolive", "", "", "Web Dev"])
    ws.append(["Also No Live", "ml", "active", "", "", "", ""])
    ws2 = wb.create_sheet("profiles")
    ws2.append(["name"])
    ws2.append(["Web Dev"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_excel_missing_live_url_in_report(client):
    data = _xlsx_bytes()
    dry = client.post("/api/import/excel", params={"dry_run": True},
                      files={"file": ("seed.xlsx", data, "application/vnd.ms-excel")})
    assert dry.status_code == 200, dry.text
    assert dry.json()["summary"]["missing_live_url"] == 2
    saved = client.post("/api/import/excel", params={"dry_run": False},
                        files={"file": ("seed.xlsx", data, "application/vnd.ms-excel")})
    assert saved.status_code == 200, saved.text
    assert saved.json()["summary"]["missing_live_url"] == 2
