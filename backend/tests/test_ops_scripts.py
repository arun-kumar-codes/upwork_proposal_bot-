"""Thin ops-script tests: handshake HTML trap + alias planner (no network/DB)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_handshake_detects_frontend_html_and_truncates():
    check = _load("check_handshake", "scripts/check_handshake.py")
    assert check.is_html_response("text/html; charset=utf-8", "{}") is True
    assert check.is_html_response("application/json", "<html>oops</html>") is True
    assert check.is_html_response("application/json", '{"ok":true}') is False
    assert len(check.truncate("x" * 500)) <= 220
    assert check.truncate("a  b") == "a b"


def test_profile_aliases_align_with_verified_identities():
    """Ops aliases use the same verified names as Hub/Bot generation."""
    norm = _load("normalize_profiles", "scripts/normalize_profiles.py")

    class FakeProfile:
        def __init__(self, name):
            self.name = name
            self.projects = []

    mapping = norm.load_aliases(ROOT / "scripts" / "profile_aliases.json")
    assert mapping["gopalan"] == "Gopalan"  # portfolio service: Gopalan Prakash
    assert mapping["gopal"] == "Gopalan"
    assert mapping["vikas"] == "Vikas Singh"  # owner-confirmed Tellaigent collaborator
    assert mapping["gopalan + vikas"] == "Gopalan + Vikas"
    profiles = [FakeProfile("Gopalan"), FakeProfile("Gopalan + Vikas"), FakeProfile("Not named")]
    _actions, unresolved = norm.plan_actions(profiles, mapping)
    assert unresolved == ["Not named"]  # verified names resolve; bucket stays reported


def test_profile_alias_planner_rename_merge_unresolved():
    norm = _load("normalize_profiles", "scripts/normalize_profiles.py")

    class FakeProfile:
        def __init__(self, name):
            self.name = name
            self.projects = []

    mapping = norm.load_aliases(ROOT / "scripts" / "profile_aliases.json")
    profiles = [FakeProfile("web-dev"), FakeProfile("Data AI"), FakeProfile("dataai"), FakeProfile("Mystery")]
    actions, unresolved = norm.plan_actions(profiles, mapping)
    kinds = {(a["action"], a["from"]) for a in actions}
    assert ("rename", "web-dev") in kinds  # no canonical yet -> rename
    assert ("merge", "dataai") in kinds  # canonical Data AI exists -> merge
    assert unresolved == ["Mystery"]  # unknown tokens are reported, untouched
