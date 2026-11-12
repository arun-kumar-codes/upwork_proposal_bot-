"""Playground: category detection, project selection, run + history endpoints."""

import pytest

from app.config import settings


def _seed(client):
    client.post("/api/profiles", json={"name": "Web Dev", "tone": "friendly"})
    projects = [
        {"title": "Shop API", "category": "web", "status": "active"},
        {"title": "Blog Theme", "category": "web", "status": "active"},
        {"title": "ML Pipeline", "category": "ml", "status": "active"},
        {"title": "Old Site", "category": "web", "status": "inactive"},
    ]
    for p in projects:
        resp = client.post("/api/projects", json={**p, "profile_names": ["Web Dev"]})
        assert resp.status_code == 201, resp.text


async def _fake_reply(**kwargs):
    titles = [p.title for p in kwargs["projects"]]
    return f"CANNED REPLY using: {', '.join(titles)}"


def test_run_simulated_detects_and_selects(client, monkeypatch):
    import app.routers.playground as pg

    _seed(client)
    monkeypatch.setattr(pg, "generate_reply", _fake_reply)
    resp = client.post(
        "/api/playground/run",
        json={
            "profile": "Web Dev",
            "client_message": "We need a web developer to build our online store",
            "mode": "simulated",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["detected_category"] == "web"
    assert data["category_source"] == "detected"
    assert data["mode"] == "simulated"
    assert data["reply"].startswith("CANNED REPLY")
    titles = [s["project"]["title"] for s in data["selected"]]
    # Relevance beats recency: the store job ranks Shop API (store need)
    # above the equally categorised but irrelevant Blog Theme.
    assert titles == ["Shop API", "Blog Theme"]
    assert all("web" in s["reason"] for s in data["selected"])
    assert "Old Site" not in titles  # inactive projects never selected

    history = client.get("/api/playground/history").json()
    assert len(history) == 1
    assert history[0]["id"] == data["run_id"]
    assert history[0]["profile_name"] == "Web Dev"
    assert "online store" in history[0]["client_message"]
    assert history[0]["reply"].startswith("CANNED REPLY")


def test_category_override_wins(client, monkeypatch):
    import app.routers.playground as pg

    _seed(client)
    monkeypatch.setattr(pg, "generate_reply", _fake_reply)
    resp = client.post(
        "/api/playground/run",
        json={
            "profile": "Web Dev",
            "client_message": "We need a web developer",
            "category_override": "ML",
            "mode": "simulated",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["detected_category"] == "ml"
    assert data["category_source"] == "override"
    assert [s["project"]["title"] for s in data["selected"]] == ["ML Pipeline"]


def test_run_unknown_profile_404(client):
    resp = client.post(
        "/api/playground/run",
        json={"profile": "Nobody", "client_message": "hello", "mode": "simulated"},
    )
    assert resp.status_code == 404


def test_run_empty_message_422(client):
    _seed(client)
    resp = client.post(
        "/api/playground/run",
        json={"profile": "Web Dev", "client_message": "   ", "mode": "simulated"},
    )
    assert resp.status_code == 422


def test_simulated_without_key_400(client, monkeypatch):
    _seed(client)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    resp = client.post(
        "/api/playground/run",
        json={
            "profile": "Web Dev",
            "client_message": "We need a web developer",
            "mode": "simulated",
        },
    )
    assert resp.status_code == 400
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_real_bot_disabled_without_bot_url(client, monkeypatch):
    import app.routers.playground as pg

    _seed(client)
    monkeypatch.setattr(settings, "BOT_URL", None)
    monkeypatch.setattr(pg, "generate_reply", _fake_reply)
    resp = client.post(
        "/api/playground/run",
        json={
            "profile": "Web Dev",
            "client_message": "We need a web developer",
            "mode": "real_bot",
        },
    )
    assert resp.status_code == 400
    assert "BOT_URL" in resp.json()["detail"]


def test_real_bot_passthrough(client, monkeypatch):
    import app.routers.playground as pg

    async def _fake_bot(**kwargs):
        return "BOT SAYS HI"

    _seed(client)
    monkeypatch.setattr(settings, "BOT_URL", "http://bot:9000")
    monkeypatch.setattr(pg, "call_real_bot", _fake_bot)
    resp = client.post(
        "/api/playground/run",
        json={
            "profile": "Web Dev",
            "client_message": "We need a web developer",
            "mode": "real_bot",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["reply"] == "BOT SAYS HI"
    assert data["mode"] == "real_bot"
    assert data["detected_category"] == "web"  # local detection still shown


def test_config_reports_flags(client, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "BOT_URL", None)
    monkeypatch.setattr(settings, "BOT_API_KEY", None)
    data = client.get("/api/playground/config").json()
    assert data == {"simulated_enabled": False, "real_bot_enabled": False}

    # URL alone is not enough: Real Bot also needs BOT_API_KEY.
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(settings, "BOT_URL", "http://bot:9000")
    monkeypatch.setattr(settings, "BOT_API_KEY", None)
    data = client.get("/api/playground/config").json()
    assert data == {"simulated_enabled": True, "real_bot_enabled": False}

    monkeypatch.setattr(settings, "BOT_API_KEY", "test-bot-key")
    data = client.get("/api/playground/config").json()
    assert data == {"simulated_enabled": True, "real_bot_enabled": True}

def test_detect_category_unit():
    from app.services.playground import detect_category

    cats = ["web", "ml"]
    assert detect_category("Build me a web app with checkout", cats) == "web"
    assert detect_category("Train an ML model on our data", cats) == "ml"
    assert detect_category("Hello, how are you?", cats) is None
    assert detect_category("anything", []) is None


def test_history_empty_initially(client):
    assert client.get("/api/playground/history").json() == []

# --- Real Bot error mapping: header sent; 401/503/connection distinct ---

import asyncio  # noqa: E402

import httpx  # noqa: E402


class _FakeBotResponse:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


def _install_fake_bot(monkeypatch, *, response=None, error=None, captured=None):
    import app.services.playground as svc

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            if captured is not None:
                captured.append({"url": url, "json": json, "headers": headers or {}})
            if error is not None:
                raise error
            return response

    monkeypatch.setattr(svc.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(svc.settings, "BOT_URL", "http://bot:9000")
    monkeypatch.setattr(svc.settings, "BOT_API_KEY", "hub-bot-key")


def _run_real_bot_via_api(client):
    return client.post(
        "/api/playground/run",
        json={
            "profile": "Web Dev",
            "client_message": "We need a web developer",
            "mode": "real_bot",
        },
    )


def test_call_real_bot_sends_api_key(client, monkeypatch):
    import app.services.playground as svc

    captured = []
    _install_fake_bot(
        monkeypatch,
        response=_FakeBotResponse(200, {"reply": "BOT OK"}),
        captured=captured,
    )
    reply = asyncio.run(
        svc.call_real_bot(
            profile_name="Web Dev", client_message="hi", category="web", projects=[]
        )
    )
    assert reply == "BOT OK"
    assert captured and captured[0]["headers"].get("X-API-Key") == "hub-bot-key"


def test_bot_401_maps_to_hub_401(client, monkeypatch):
    _seed(client)
    _install_fake_bot(
        monkeypatch,
        response=_FakeBotResponse(401, {"success": False, "error": "Invalid API key"}),
    )
    resp = _run_real_bot_via_api(client)
    assert resp.status_code == 401, resp.text
    assert "key mismatch" in resp.json()["detail"].lower()


def test_bot_503_maps_to_hub_503(client, monkeypatch):
    _seed(client)
    _install_fake_bot(
        monkeypatch,
        response=_FakeBotResponse(503, {"success": False, "error": "BOT_API_KEY not configured"}),
    )
    resp = _run_real_bot_via_api(client)
    assert resp.status_code == 503, resp.text
    assert "not configured" in resp.json()["detail"].lower()


def test_bot_connection_error_maps_to_502(client, monkeypatch):
    _seed(client)
    req = httpx.Request("POST", "http://bot:9000/generate")
    _install_fake_bot(monkeypatch, error=httpx.ConnectError("boom", request=req))
    resp = _run_real_bot_via_api(client)
    assert resp.status_code == 502, resp.text
    assert "unreachable" in resp.json()["detail"].lower()


# --- Profile isolation: Hub forwards ownership; no-project runs stay safe ---

def test_call_real_bot_payload_carries_profile_ownership(monkeypatch):
    """The Bot can only honour profile isolation if ownership travels with projects."""
    import app.services.playground as svc
    from app.models import Profile, Project

    captured = []
    _install_fake_bot(
        monkeypatch,
        response=_FakeBotResponse(200, {"reply": "BOT OK"}),
        captured=captured,
    )
    project = Project(
        title="Shop",
        category="web",
        github_url="https://github.com/demo/shop",
        live_url="https://shop.example.com",
        description="store for clients",
        result="live for real clients",
        tech_stack=["react"],
        profiles=[Profile(name="Web Dev")],
    )
    reply = asyncio.run(
        svc.call_real_bot(
            profile_name="Web Dev", client_message="hi", category="web", projects=[project]
        )
    )
    assert reply == "BOT OK"
    sent = captured[0]["json"]["projects"][0]
    assert sent["profiles"] == ["Web Dev"]
    assert sent["description"] == "store for clients"
    assert sent["result"] == "live for real clients"
    assert sent["tech_stack"] == ["react"]


GOPALAN_PORTFOLIO = "http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b"
VIKAS_PORTFOLIOS = (
    "http://116.202.210.102:3700/portfolio/6949313330db86ebbad04a35",  # Vikas Kumar
    "http://116.202.210.102:3700/portfolio/6949306730db86ebbad04a17",  # Vikas Singh
)


def test_gopalan_portfolio_mapping():
    """Hub 'Gopalan' is Gopalan Prakash (portfolio service verifies the ID)."""
    from app.services.playground import resolve_person

    assert resolve_person("Gopalan") == ("Gopalan", GOPALAN_PORTFOLIO)
    # Combined token: first contributor owns the proposal; people never merge.
    assert resolve_person("Gopalan + Vikas") == ("Gopalan", GOPALAN_PORTFOLIO)
    # Owner confirmed the Tellaigent collaborator is Vikas Singh (not Kumar).
    assert resolve_person("Vikas Singh") == ("Vikas Singh", VIKAS_PORTFOLIOS[1])
    # Bare "Vikas" is NOT globally aliased to Singh: no silent assignment.
    assert resolve_person("Vikas") == ("Vikas", None)
    # Vikas Kumar keeps his own separate mapping and full-name sign-off.
    assert resolve_person("Vikas Kumar") == ("Vikas Kumar", VIKAS_PORTFOLIOS[0])
    # Existing mappings are unchanged.
    assert resolve_person("Arun")[1] == (
        "http://116.202.210.102:3700/portfolio/69492dc930db86ebbad04a03"
    )
    assert resolve_person("Faizal / LYT")[1] == (
        "http://116.202.210.102:3700/portfolio/695b83cff3cd570bc25c4db8"
    )


def test_gopalan_template_includes_verified_portfolio_only():
    from app.models import Profile, Project
    from app.services.playground import resolve_collaborators, template_reply

    assert resolve_collaborators("Gopalan + Vikas") == [("Vikas Singh", VIKAS_PORTFOLIOS[1])]
    assert resolve_collaborators("Gopalan") == []
    assert resolve_collaborators("Faizal / LYT") == []  # same person, not a collaborator
    # People-list parsing is restricted to the verified combined profile:
    # lookalike names never inherit Vikas Singh's portfolio.
    assert resolve_collaborators("Kishan / Vikas") == []
    assert resolve_collaborators("Newdev + Vikas") == []
    assert resolve_collaborators("Atul, Vikas") == []

    for profile_name in ("Gopalan", "Gopalan + Vikas"):
        reply = template_reply(
            profile=Profile(name=profile_name, skills=[]),
            projects=[
                Project(
                    title="Sydon",
                    category="ai",
                    live_url="https://sydon.ai/",
                    description="Amazon seller account-health system",
                    result="",
                    tech_stack=[],
                )
            ],
            client_message="We need a voice AI agent",
            category="ai",
        )
        assert f"please review my portfolio: {GOPALAN_PORTFOLIO}" in reply
        assert reply.rstrip().endswith("Gopalan")
        assert VIKAS_PORTFOLIOS[0] not in reply  # Vikas Kumar: different person
        if profile_name == "Gopalan + Vikas":
            # Both verified contributors represented, each with their own link.
            assert f"please review Vikas Singh's portfolio: {VIKAS_PORTFOLIOS[1]}" in reply
        else:
            assert VIKAS_PORTFOLIOS[1] not in reply

    singh = template_reply(
        profile=Profile(name="Vikas Singh", skills=[]),
        projects=[
            Project(
                title="Tellaigent",
                category="ai",
                live_url="https://tellaigent.ai",
                description="Platform for AI agents",
                result="",
                tech_stack=[],
            )
        ],
        client_message="We need an AI agent",
        category="ai",
    )
    assert f"please review my portfolio: {VIKAS_PORTFOLIOS[1]}" in singh
    assert VIKAS_PORTFOLIOS[0] not in singh and GOPALAN_PORTFOLIO not in singh
    assert singh.rstrip().endswith("Vikas Singh")  # full verified sign-off


def _combined_fake_llm(reply_text: str, captured: dict):
    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": reply_text}}]}

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

    return _Client


def test_combined_profile_api_with_mocked_llm(client, monkeypatch):
    """API-level Simulated flow for 'Gopalan + Vikas': prompt, validator, reply."""
    import app.services.playground as svc

    client.post("/api/profiles", json={"name": "Gopalan + Vikas"})
    resp = client.post(
        "/api/projects",
        json={
            "title": "Tellaigent",
            "category": "ai",
            "status": "active",
            "live_url": "https://tellaigent.ai",
            "description": "Platform for AI agents",
            "profile_names": ["Gopalan + Vikas"],
        },
    )
    assert resp.status_code == 201, resp.text
    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-openai")

    # No "I work with …" claim: this freelancer has no verified skills in
    # Hub data, so a skill claim would fail the accuracy validator.
    valid_reply = (
        "hey there\n"
        "I am Gopalan a AI dev\n"
        "recently I worked on Tellaigent https://tellaigent.ai\n"
        "it is live right now and real users use it daily.\n"
        f"please review my portfolio: {GOPALAN_PORTFOLIO}\n"
        f"please review Vikas Singh's portfolio: {VIKAS_PORTFOLIOS[1]}\n"
        "Please let me know when we can proceed further.\n"
        "Best regards\n"
        "Gopalan"
    )
    captured: dict = {}
    monkeypatch.setattr(
        svc.httpx, "AsyncClient", _combined_fake_llm(valid_reply, captured)
    )
    resp = client.post(
        "/api/playground/run",
        json={
            "profile": "Gopalan + Vikas",
            "client_message": "We need a voice AI agent",
            "mode": "simulated",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"] == valid_reply  # valid LLM output ships as-is

    prompt_text = str(captured["json"])
    assert f"please review Vikas Singh's portfolio: {VIKAS_PORTFOLIOS[1]}" in prompt_text
    assert VIKAS_PORTFOLIOS[1] in prompt_text  # Singh link is allowed/instructed
    assert VIKAS_PORTFOLIOS[0] not in prompt_text  # Kumar never enters the prompt

    # LLM output missing the collaborator link fails validation -> the
    # deterministic template ships instead, still with both verified links.
    missing_collab = valid_reply.replace(
        f"please review Vikas Singh's portfolio: {VIKAS_PORTFOLIOS[1]}\n", ""
    )
    monkeypatch.setattr(
        svc.httpx, "AsyncClient", _combined_fake_llm(missing_collab, {})
    )
    resp = client.post(
        "/api/playground/run",
        json={
            "profile": "Gopalan + Vikas",
            "client_message": "We need a voice AI agent",
            "mode": "simulated",
        },
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert f"please review my portfolio: {GOPALAN_PORTFOLIO}" in reply
    assert f"please review Vikas Singh's portfolio: {VIKAS_PORTFOLIOS[1]}" in reply
    assert VIKAS_PORTFOLIOS[0] not in reply


def test_unrelated_combined_name_api_gets_no_singh_portfolio(client, monkeypatch):
    """'Kishan / Vikas' is not a verified combined profile: no Singh credit."""
    import app.services.playground as svc

    client.post("/api/profiles", json={"name": "Kishan / Vikas"})
    resp = client.post(
        "/api/projects",
        json={
            "title": "Demo App",
            "category": "ai",
            "status": "active",
            "live_url": "https://demo.example.com",
            "profile_names": ["Kishan / Vikas"],
        },
    )
    assert resp.status_code == 201, resp.text
    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-openai")
    corporate = "Hi there, Thank you for reaching out! Looking forward to connecting."
    monkeypatch.setattr(
        svc.httpx, "AsyncClient", _combined_fake_llm(corporate, {})
    )
    resp = client.post(
        "/api/playground/run",
        json={
            "profile": "Kishan / Vikas",
            "client_message": "We need an AI agent",
            "mode": "simulated",
        },
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()["reply"]
    assert VIKAS_PORTFOLIOS[1] not in reply  # Singh never inherited
    assert VIKAS_PORTFOLIOS[0] not in reply


def test_profile_name_validation_unit():
    from app.services.profile_names import is_valid_profile_name

    for bad in ["", "   ", "Not", "Not named", "Unknown", "N/A", "none", None, "-"]:
        assert not is_valid_profile_name(bad), repr(bad)
    for good in ["Atul", "Faizal / LYT", "Gopalan + Vikas", "Web Dev", "Vikas Kumar"]:
        assert is_valid_profile_name(good), repr(good)


def test_playground_rejects_placeholder_profile(client, monkeypatch):
    """The blank-profile bucket must never sign a proposal, in either mode."""
    import app.routers.playground as pg

    async def _boom(**kwargs):
        raise AssertionError("generation must not run for an invalid identity")

    client.post("/api/profiles", json={"name": "Not named"})
    resp = client.post(
        "/api/projects",
        json={"title": "Orphan Tool", "category": "web", "status": "active",
              "profile_names": ["Not named"]},
    )
    assert resp.status_code == 201, resp.text
    monkeypatch.setattr(pg, "generate_reply", _boom)
    monkeypatch.setattr(pg, "call_real_bot", _boom)
    for mode in ("simulated", "real_bot"):
        resp = client.post(
            "/api/playground/run",
            json={"profile": "Not named", "client_message": "Need a web app", "mode": mode},
        )
        assert resp.status_code == 400, (mode, resp.text)
        assert "invalid" in resp.json()["detail"].lower()


def test_template_reply_never_leaks_internal_notes():
    """Excel Notes land in Project.result; proposals must only use public text."""
    from app.models import Profile, Project
    from app.services.playground import public_proof_text, template_reply

    internal = Project(
        title="Trading App",
        category="ai",
        live_url="https://trading.example.com",
        description="Rule-based trading app for clients",
        result="Live dashboard IP. Not an ML model. Team confirmed Active (Slack).",
        tech_stack=[],
    )
    assert public_proof_text(internal) == "Rule-based trading app for clients"
    reply = template_reply(
        profile=Profile(name="Atul", skills=[]),
        projects=[internal],
        client_message="We need an AI trading tool",
        category="ai",
    )
    assert "Git URL" not in reply and "Slack" not in reply and "Team confirmed" not in reply
    assert "Rule-based trading app for clients." in reply  # legit description intact

    # A clean verified result is preserved, not stripped wholesale.
    clean = Project(
        title="Store Builder",
        category="web",
        live_url="https://store.example.com",
        description="store builder made with React",
        result="client sales went up after launch",
        tech_stack=[],
    )
    assert public_proof_text(clean) == "client sales went up after launch"

    # Internal-only with no description -> nothing client-facing remains.
    bare = Project(
        title="Secret Tool",
        category="ai",
        live_url="https://secret.example.com",
        description=None,
        result="Live product. Git URL not given.",
        tech_stack=[],
    )
    assert public_proof_text(bare) == ""
    reply = template_reply(
        profile=Profile(name="Atul", skills=[]),
        projects=[bare],
        client_message="We need an AI tool",
        category="ai",
    )
    assert "Git URL not given" not in reply
    assert "it is live right now and real users use it daily." in reply


def test_simulated_llm_prompt_excludes_internal_notes(client, monkeypatch):
    """Internal Notes must reach neither the LLM prompt nor the final reply."""
    import app.services.playground as svc
    from app.models import Profile, Project

    captured = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "Hi there, Thank you for reaching out!"}}]}

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

    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)
    reply = asyncio.run(
        svc.generate_reply(
            profile=Profile(name="Atul", skills=[]),
            projects=[
                Project(
                    title="Trading App",
                    category="ai",
                    github_url="https://github.com/demo/trading",
                    live_url="https://trading.example.com",
                    description="Rule-based trading app for clients",
                    result="Live dashboard IP. Team confirmed Active (Slack). Git URL not given.",
                    tech_stack=[],
                )
            ],
            client_message="We need an AI trading tool",
        )
    )
    prompt_text = str(captured["json"])
    assert "Team confirmed" not in prompt_text and "Slack" not in prompt_text
    assert "Git URL not given" not in prompt_text
    assert "Rule-based trading app for clients" in prompt_text  # legit info preserved
    assert "Team confirmed" not in reply and "Slack" not in reply
    assert "Git URL not given" not in reply


# --- Proposal quality: relevance, personalisation, accuracy -----------------

def test_relevant_project_beats_most_recent():
    """The proof project must match the job, not just be the newest."""
    from app.models import Project
    from app.services.playground import select_projects

    gaming = Project(
        title="No Limit Gaming", category="full stack",
        live_url="https://gaming.example.com",
        description="Sports prediction site with virtual chips", tech_stack=[],
    )
    deals = Project(
        title="AhorraTya", category="full stack",
        live_url="https://deals.example.com",
        description="Deals site so shoppers can find store promotions and compare offers",
        tech_stack=[],
    )
    picked = select_projects(
        [gaming, deals], None, 3,
        client_message="Hi I am Aparna we need a web app for our store where customers can browse products and pay online",
    )
    assert picked[0][0].title == "AhorraTya"
    assert "store" in picked[0][1]


def test_template_adapts_to_job_and_never_invents_skills():
    """Different jobs read differently; an unverified ask is never a claim."""
    from app.models import Profile, Project
    from app.services.playground import template_reply

    profile = Profile(name="Arun", skills=[])
    projects = [
        Project(
            title="AhorraTya", category="full stack",
            live_url="https://deals.example.com",
            description="Deals site so shoppers can find store promotions",
            result="", tech_stack=[],
        )
    ]
    store = template_reply(
        profile=profile, projects=projects,
        client_message="Hi I am Aparna we need a React web app for our store with checkout",
        category="web",
    )
    assert store.startswith("hey Aparna")
    assert "store where customers can browse and pay" in store
    assert "product pages and checkout" in store
    assert "I work with React" not in store  # React is the client's ask only
    assert "modern web tools" not in store  # no generic filler claim

    hospital = template_reply(
        profile=profile, projects=projects,
        client_message="We need a CRM for our hospital front desk to manage patient appointments",
        category="web",
    )
    assert "keeps customers and bookings together" in hospital
    assert "booking and follow up flow" in hospital
    assert hospital != store

    # A verified skill may be claimed, and only then.
    skilled = template_reply(
        profile=Profile(name="Arun", skills=["React"]), projects=projects,
        client_message="We need a React web app for our store",
        category="web",
    )
    assert "I work with React" in skilled


def test_validator_rejects_unverified_skill_claims():
    from app.services.playground import validate_reply

    base = (
        "hey there\nI am Arun a web dev I work with {skills}\n"
        "recently I worked on Deals https://deals.example.com\n"
        "please review my portfolio: http://116.202.210.102:3700/portfolio/69492dc930db86ebbad04a03"
    )
    ctx = dict(
        portfolio="http://116.202.210.102:3700/portfolio/69492dc930db86ebbad04a03",
        live_urls=["https://deals.example.com"],
    )
    assert not validate_reply(
        base.format(skills="React and Python"), verified_techs_list=[], **ctx
    )
    assert validate_reply(
        base.format(skills="React"), verified_techs_list=["react"], **ctx
    )


def test_llm_prompt_carries_analysis_and_unverified_claim_falls_back(client, monkeypatch):
    """Simulated brief separates verified skills from client asks."""
    import app.services.playground as svc
    from app.models import Profile, Project

    captured = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": (
                "hey Sara\nI am Atul a AI dev I work with React and Node.js\n"
                "recently I worked on Lomex AI https://lomex.ai\n"
                "please review my portfolio: http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff"
            )}}]}

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

    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)
    reply = asyncio.run(
        svc.generate_reply(
            profile=Profile(name="Atul", skills=[]),
            projects=[
                Project(
                    title="Lomex AI", category="ai + full stack",
                    live_url="https://lomex.ai",
                    description="RAG assistant. Tenants upload documents and ask questions",
                    result="", tech_stack=[],
                )
            ],
            client_message="Hi I am Sara we need an AI assistant that answers questions from our own documents and manuals",
        )
    )
    prompt_text = str(captured["json"])
    assert "answers from your documents" in prompt_text
    assert "Verified skills you may claim: none listed" in prompt_text
    assert "do not claim unless verified" in prompt_text
    # The LLM claimed React with no verified source: the personalised
    # deterministic template ships instead, still grounded in Lomex.
    assert "I work with React" not in reply
    assert "Lomex AI https://lomex.ai" in reply
    assert "stops hunting through files" in reply


def test_simulated_no_projects_never_calls_llm(monkeypatch):
    """Zero eligible projects -> deterministic safe template, no invented proof."""
    import app.services.playground as svc
    from app.models import Profile

    class _Boom:
        def __init__(self, *a, **kw):
            raise AssertionError("LLM must not be called when there are no projects")

    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(svc.httpx, "AsyncClient", _Boom)
    reply = asyncio.run(
        svc.generate_reply(
            profile=Profile(name="Deepanshu", skills=[]),
            projects=[],
            client_message="We need an AI automation tool",
        )
    )
    assert "I am Deepanshu" in reply
    assert "recently" not in reply  # no fabricated experience
    assert (
        "please review my portfolio: "
        "http://116.202.210.102:3700/portfolio/69492f8e30db86ebbad04a07"
    ) in reply
    assert "github.com" not in reply


# --- Hardening: distinctive proof, internal text, honest relevance ----------

VOICE_JOB = (
    "Hi I am Sara we run a real estate agency and we need a voice agent "
    "that calls leads on the phone and books meetings on our calendar so "
    "our team stops chasing calls all day"
)


def _voice_projects():
    from app.models import Project

    cofounder = Project(
        title="AI Cofounder", category="ai + full stack",
        live_url="https://agent.example.com",
        description="AI Cofounder agent that helps entrepreneurs brainstorm ideas and market analysis",
        result="", tech_stack=[],
    )
    tara = Project(
        title="Tara", category="ai + full stack + automation",
        live_url="https://tara.example.com",
        description="Business automation through WhatsApp or voice. Connects tools for email and follow ups",
        result="", tech_stack=[],
    )
    return cofounder, tara


def test_voice_claim_requires_distinctive_evidence():
    """Smoke regression (Atul x voice): 'agent' alone never proves voice."""
    from app.models import Profile
    from app.services.playground import select_projects, template_reply

    cofounder, tara = _voice_projects()
    # Real voice proof outranks the newer generic agent project.
    picked = select_projects([cofounder, tara], None, 3, client_message=VOICE_JOB)
    assert picked[0][0].title == "Tara"
    assert "covers your voice calls and booking need" in picked[0][1]

    strong = template_reply(
        profile=Profile(name="Atul", skills=[]), projects=[tara],
        client_message=VOICE_JOB, category=None,
    )
    assert "covers your voice calls and booking need" in strong

    # Generic agent work may be cited only as related AI experience.
    weak = template_reply(
        profile=Profile(name="Atul", skills=[]), projects=[cofounder],
        client_message=VOICE_JOB, category=None,
    )
    assert "covers your voice calls and booking need" not in weak
    # Secondary-need coverage is no longer the headline fit claim: the
    # primary need (voice) is only RELATED for this project, so the
    # template uses related wording (Atul secondary-need case).
    assert "covers your AI agent work need" not in weak
    assert "shows related AI agent work" in weak


def test_voice_weak_only_wording_never_implies_telephony():
    """A weak-only match gets related wording, not a voice capability claim."""
    from app.models import Profile, Project
    from app.services.playground import template_reply

    helper = Project(
        title="Lead Helper", category="ai",
        live_url="https://helper.example.com",
        description="agent dashboard that helps teams track leads",
        result="", tech_stack=[],
    )
    reply = template_reply(
        profile=Profile(name="Aayush", skills=[]), projects=[helper],
        client_message="We need a voice agent to answer our phone calls",
        category=None,
    )
    assert "covers your voice" not in reply
    assert "shows related AI agent work" in reply


def test_internal_status_and_collaboration_text_never_leaks():
    """Smoke regression: 'Doc status' / 'Shared by' yield to descriptions."""
    from app.models import Profile, Project
    from app.services.playground import public_proof_text, template_reply

    lomex = Project(
        title="Lomex AI", category="ai + full stack",
        live_url="https://lomex.ai",
        description="Multi-tenant RAG assistant. Each tenant uploads documents and asks questions",
        result="Doc status: In-Progress.", tech_stack=[],
    )
    assert public_proof_text(lomex).startswith("Multi-tenant RAG assistant")
    reply = template_reply(
        profile=Profile(name="Atul", skills=[]), projects=[lomex],
        client_message="Hi I am Sara we need an AI assistant that answers questions from our own documents and manuals",
        category="ai",
    )
    assert "Doc status" not in reply and "In-Progress" not in reply
    assert "uploads documents and asks questions" in reply

    go = Project(
        title="Tellaigent GO", category="ai + full stack + automation",
        live_url="https://go.example.com",
        description="AI sales rep. Makes outbound calls and books Google Calendar meetings",
        result="Live IP app. Shared by Gopalan and Vikas.", tech_stack=[],
    )
    assert "Makes outbound calls" in public_proof_text(go)
    assert "Shared by" not in public_proof_text(go)

    # Legitimate public results are preserved, not stripped.
    legit = Project(
        title="Clinic Agent", category="ai",
        live_url="https://clinic.example.com",
        description="phone agent for clinics",
        result="Live phone agents are answering calls for the clinic",
        tech_stack=[],
    )
    assert public_proof_text(legit) == "Live phone agents are answering calls for the clinic"


def test_shopify_claim_requires_real_store_evidence():
    """Smoke regression: Arun x store stays positive; unrelated stays honest."""
    from app.models import Profile, Project
    from app.services.playground import template_reply

    job = "Hi I am Lena we need a Shopify store where customers can browse our products and pay online with a smooth checkout and cart"
    deals = Project(
        title="AhorraTya", category="full stack",
        live_url="https://deals.example.com",
        description="Deals site so shoppers can find store promotions and compare offers",
        result="", tech_stack=[],
    )
    positive = template_reply(
        profile=Profile(name="Arun", skills=[]), projects=[deals],
        client_message=job, category=None,
    )
    assert "covers your store and checkout need" in positive

    cofounder, _tara = _voice_projects()
    negative = template_reply(
        profile=Profile(name="Atul", skills=[]), projects=[cofounder],
        client_message=job, category=None,
    )
    assert "covers your store and checkout need" not in negative
    assert "recent live work I shipped" in negative  # honest, no store claim


def test_category_detection_covers_voice_store_dashboard():
    from app.services.playground import detect_category

    cats = ["ai", "ai + full stack", "ai + full stack + automation", "automation", "full stack"]
    assert detect_category(VOICE_JOB, cats) == "voice"
    assert detect_category(
        "Hi I am Lena we need a Shopify store where customers can browse products and pay online", cats
    ) == "shopify"
    assert detect_category(
        "Hi I am Raj we need a dashboard with live trading charts and reporting", cats
    ) == "dashboard"
    # Existing behaviour is unchanged.
    assert detect_category("Build me a web app with checkout", ["web", "ml"]) == "web"
    assert detect_category("Hello, how are you?", cats) is None


def test_validator_and_llm_guard_reject_unsupported_voice_claim(monkeypatch):
    """An LLM may not claim voice coverage the cited project cannot prove."""
    import app.services.playground as svc
    from app.models import Profile
    from app.services.playground import validate_reply

    cofounder, _tara = _voice_projects()
    ctx = dict(
        portfolio="http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff",
        live_urls=["https://agent.example.com"],
    )
    claim = (
        "hey Sara\nI am Atul a full stack dev\n"
        "recently I worked on AI Cofounder https://agent.example.com\n"
        "I picked this one because it already covers your voice calls and booking need.\n"
        "please review my portfolio: http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff"
    )
    assert not validate_reply(claim, unsupported_claim_labels=["voice calls and booking"], **ctx)
    assert validate_reply(claim, unsupported_claim_labels=[], **ctx)

    captured = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": claim}}]}

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

    monkeypatch.setattr(svc.settings, "OPENAI_API_KEY", "test-openai")
    monkeypatch.setattr(svc.httpx, "AsyncClient", _Client)
    reply = asyncio.run(
        svc.generate_reply(
            profile=Profile(name="Atul", skills=[]),
            projects=[cofounder],
            client_message=VOICE_JOB,
        )
    )
    # Unsupported LLM claim rejected: the honest template ships instead.
    assert "covers your voice calls and booking need" not in reply
    assert "covers your AI agent work need" not in reply
    assert "shows related AI agent work" in reply


# The four Simulated-mode relevance bridges from the 176-proposal live
# evaluation (proposal-quality-evaluation-report.md), comma-free adaptations
# so only the evidence-strength rule can reject them.
_EVAL_BRIDGES = [
    "this experience is directly related to the automation of manual work.",
    "this project has relevant dashboards experience which aligns with your needs.",
    "this project aligns with your need for automating manual work.",
    "this project aligns with your needs as it involved user management.",
    "this project can match your needs exactly.",
    "this project closely aligns with your requirements.",
]


def _bridge_text(sentence: str) -> str:
    return (
        "hey Sara\nI am Atul a full stack dev\n"
        "recently I worked on AI Cofounder https://agent.example.com\n"
        f"{sentence}\n"
        "please review my portfolio: http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff"
    )


def test_strength_language_rejected_below_cover_tier():
    """Negative: coverage-strength wording fails at RELATED and NONE tiers."""
    from app.services.playground import validate_reply

    ctx = dict(
        portfolio="http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff",
        live_urls=["https://agent.example.com"],
    )
    for sentence in _EVAL_BRIDGES:
        text = _bridge_text(sentence)
        assert not validate_reply(text, claim_tier="RELATED", **ctx), sentence
        assert not validate_reply(text, claim_tier="NONE", **ctx), sentence


def test_strength_language_allowed_at_cover_and_honest_related_passes():
    """Positive: COVER tier may claim coverage; honest related wording passes."""
    from app.services.playground import validate_reply

    ctx = dict(
        portfolio="http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff",
        live_urls=["https://agent.example.com"],
    )
    for sentence in _EVAL_BRIDGES:
        assert validate_reply(_bridge_text(sentence), claim_tier="COVER", **ctx), sentence
    honest = _bridge_text("I picked this one because it is my closest related work.")
    assert validate_reply(honest, claim_tier="RELATED", **ctx)
    assert validate_reply(honest, claim_tier="NONE", **ctx)
    # Legacy callers without a tier keep the previous behaviour.
    assert validate_reply(_bridge_text(_EVAL_BRIDGES[0]), **ctx)


def test_claim_tier_reflects_scorer_reasons():
    """Tiers come from the scorer: distinctive proof COVER, none NONE."""
    from app.models import Project
    from app.services.playground import analyze_job, claim_tier

    _cofounder, tara = _voice_projects()
    analysis = analyze_job(VOICE_JOB, None)
    assert claim_tier(tara, analysis, None) == "COVER"
    assert claim_tier(None, analysis, None) == "NONE"
    unrelated = Project(
        title="PrimeTime", category="web",
        live_url="https://primetime.example.com",
        description="Kitchen timer app for home cooks with recipes",
        result="", tech_stack=[],
    )
    n8n_analysis = analyze_job(
        "Hi I am Jonas we need an n8n automation workflow that watches our "
        "CRM for new leads and sends personalised follow up emails",
        "automation",
    )
    assert claim_tier(unrelated, n8n_analysis, "automation") == "NONE"


def test_need_tiers_primary_secondary_and_validator_enforcement():
    """Atul secondary-need case: tiers are per need, enforced per need.

    AI Cofounder covers the secondary "AI agent work" need for a voice job
    but is only RELATED for the primary voice need. The primary tier gates
    strength language, and a covers-claim for any need requires that
    need's own COVER tier.
    """
    from app.services.playground import (
        analyze_job,
        claim_tier,
        need_tiers,
        validate_reply,
    )

    cofounder, tara = _voice_projects()
    analysis = analyze_job(VOICE_JOB, None)
    tiers = need_tiers(cofounder, analysis, None)
    assert tiers["AI agent work"] == "COVER"
    assert tiers["voice calls and booking"] == "RELATED"
    assert claim_tier(cofounder, analysis, None) == "RELATED"
    assert claim_tier(tara, analysis, None) == "COVER"

    ctx = dict(
        portfolio="http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff",
        live_urls=["https://agent.example.com"],
    )
    atul_claim = _bridge_text(
        "I picked this one because it already covers your website build need."
    )
    # The claimed need's own tier decides: RELATED rejects, COVER allows.
    assert not validate_reply(
        atul_claim, need_tiers_map={"website build": "RELATED"}, **ctx
    )
    assert validate_reply(
        atul_claim, need_tiers_map={"website build": "COVER"}, **ctx
    )
    # Primary RELATED also blocks the same sentence via the strength gate,
    # even when a secondary need is COVER.
    assert not validate_reply(
        atul_claim,
        claim_tier="RELATED",
        need_tiers_map={"website build": "COVER", "AI agent work": "COVER"},
        **ctx,
    )


_OLD_GENERIC_CLOSINGS = (
    "I can start right away and I will share progress in small steps",
    "you will talk directly with the person writing the code so nothing gets lost in between",
)


def test_template_closing_is_contextual_by_need_and_tier():
    """Closings name the job's first checkpoint and respect evidence tier."""
    from app.models import Profile
    from app.services.playground import template_reply

    cofounder, tara = _voice_projects()
    profile = Profile(name="Atul", skills=[])

    cover = template_reply(
        profile=profile, projects=[tara], client_message=VOICE_JOB, category=None
    )
    assert "You will hear test calls before the agent handles live leads." in cover
    assert "The project shown above gives that checkpoint a proven starting point." in cover

    related = template_reply(
        profile=profile, projects=[cofounder], client_message=VOICE_JOB, category=None
    )
    assert "You will hear test calls before the agent handles live leads." in related
    assert "The related work gives useful context" in related
    assert "proven starting point" not in related

    none = template_reply(
        profile=Profile(name="Deepanshu", skills=[]),
        projects=[],
        client_message=VOICE_JOB,
        category=None,
    )
    assert "You will hear test calls before the agent handles live leads." in none
    assert "That checkpoint will prove the parts specific to your job" in none

    docs = template_reply(
        profile=profile,
        projects=[cofounder],
        client_message=(
            "Hi I am Sara we run a construction firm and we need an AI assistant "
            "that answers questions from our own documents and manuals so staff "
            "stop searching PDFs all day and it should cite the source document"
        ),
        category=None,
    )
    assert "You will test answers from your real documents before a wider rollout." in docs
    assert "You will hear test calls" not in docs

    for text in (cover, related, none, docs):
        for generic in _OLD_GENERIC_CLOSINGS:
            assert generic not in text
        assert "Please let me know when we can proceed further." in text


_N8N_JOB = (
    "Hi I am Jonas we need an n8n automation workflow that watches our "
    "CRM for new leads and sends personalised follow up emails "
    "automatically without anyone doing manual work"
)
_CHATBOT_JOB = (
    "Hi I am Tom we need an AI agent chatbot on our website that "
    "answers customer questions and books appointments for our clinic "
    "without our front desk getting involved"
)


def _arun_projects():
    from app.models import Project

    return [
        Project(
            title="No Limit Gaming", category="ai + full stack",
            live_url="https://nolimitgaming.bet/signin",
            description="Sports prediction site. Users predict with virtual "
                        "chips that have no cash value. Includes an AI advisory.",
            result="", tech_stack=[],
        ),
        Project(
            title="InjuryConnect", category="full stack",
            live_url="https://injuryconnect.example.com",
            description="Platform connecting injured workers with clinics "
                        "and legal help.",
            result="", tech_stack=[],
        ),
        Project(
            title="AhorraTya", category="full stack",
            live_url="https://ahorratya.example.com",
            description="Savings and deals app for shoppers.",
            result="", tech_stack=[],
        ),
    ]


def test_relevance_floor_arun_n8n_zero_reason_selects_nothing():
    """Arun x n8n: all three projects score with zero reasons -> []."""
    from app.services.playground import score_project, analyze_job, select_projects

    projects = _arun_projects()
    analysis = analyze_job(_N8N_JOB, "automation")
    for p in projects:
        _score, reasons = score_project(p, analysis, "automation")
        assert reasons == [], (p.title, reasons)
    assert select_projects(projects, "automation", 3, client_message=_N8N_JOB) == []


def test_relevance_floor_preserves_arun_chatbot_legitimate_match():
    """Arun x chatbot: No Limit Gaming has real covers-reasons and stays."""
    from app.services.playground import select_projects

    picked = select_projects(
        _arun_projects(), "ai", 3, client_message=_CHATBOT_JOB
    )
    assert picked
    assert picked[0][0].title == "No Limit Gaming"
    assert "covers your AI agent work need" in picked[0][1]


def test_relevance_floor_zero_reason_and_related_reason_boundary():
    """Zero-reason projects drop out; any real reason keeps a project."""
    from app.models import Project
    from app.services.playground import select_projects

    kitchen = Project(
        title="PrimeTime", category="web",
        live_url="https://primetime.example.com",
        description="Kitchen timer app for home cooks with recipes",
        result="", tech_stack=[],
    )
    assert select_projects([kitchen], "automation", 3, client_message=_N8N_JOB) == []
    picked = select_projects(
        [kitchen] + _arun_projects(), "ai", 3, client_message=_CHATBOT_JOB
    )
    assert [p.title for p, _ in picked] == ["No Limit Gaming"]

