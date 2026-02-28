"""Tests for the SRD 5.2 ruleset module and /rulesets API endpoints."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import srd
from server.agents.srd import (
    KNOWN_RULESET_IDS,
    RULESETS,
    SRD_52_DATA,
    build_ruleset_prompt_context,
    get_ruleset_context,
)
from server.auth import create_access_token


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str) -> db.User:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return existing
    user = db.create_user(
        email=email,
        password="secret",
        username=email.split("@")[0],
        profile={"name": email.split("@")[0], "email": email},
    )
    assert user.verification_token
    db.verify_user(email, user.verification_token)
    return user


# ---------------------------------------------------------------------------
# Unit tests for static data integrity
# ---------------------------------------------------------------------------

def test_srd52_data_has_required_keys():
    required = {"attribution", "resolution", "proficiency_bonus", "ability_scores", "skills", "classes", "conditions", "combat_actions", "species"}
    assert required.issubset(SRD_52_DATA.keys())


def test_srd52_has_all_six_ability_scores():
    assert set(SRD_52_DATA["ability_scores"].keys()) == {"STR", "DEX", "CON", "INT", "WIS", "CHA"}


def test_srd52_has_18_skills():
    assert len(SRD_52_DATA["skills"]) == 18


def test_srd52_all_skills_have_valid_ability():
    valid = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}
    for skill, ability in SRD_52_DATA["skills"].items():
        assert ability in valid, f"Skill '{skill}' has invalid ability '{ability}'"


def test_srd52_has_13_classes():
    assert len(SRD_52_DATA["classes"]) == 13


def test_srd52_classes_include_artificer():
    assert "Artificer" in SRD_52_DATA["classes"]


def test_srd52_has_15_conditions():
    assert len(SRD_52_DATA["conditions"]) == 15


def test_srd52_conditions_include_all_standard():
    expected = {
        "Blinded", "Charmed", "Deafened", "Exhaustion", "Frightened",
        "Grappled", "Incapacitated", "Invisible", "Paralyzed", "Petrified",
        "Poisoned", "Prone", "Restrained", "Stunned", "Unconscious",
    }
    assert expected == set(SRD_52_DATA["conditions"].keys())


def test_srd52_has_9_species():
    assert len(SRD_52_DATA["species"]) == 9


def test_srd52_attribution_present():
    assert "CC-BY-4.0" in SRD_52_DATA["attribution"]
    assert "Wizards of the Coast" in SRD_52_DATA["attribution"]


def test_known_ruleset_ids_includes_srd():
    assert "srd-5.2" in KNOWN_RULESET_IDS
    assert "custom" in KNOWN_RULESET_IDS


def test_rulesets_registry_includes_srd():
    assert "srd-5.2" in RULESETS
    rs = RULESETS["srd-5.2"]
    assert rs["license"] == "CC-BY-4.0"
    assert rs["publisher"] == "Wizards of the Coast"


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

def test_get_ruleset_context_srd52():
    ctx = get_ruleset_context("srd-5.2")
    assert ctx["ruleset_id"] == "srd-5.2"
    assert "skills" in ctx
    assert len(ctx["classes"]) == 13
    assert len(ctx["conditions"]) == 15


def test_get_ruleset_context_unknown_returns_empty():
    assert get_ruleset_context("unknown-system") == {}


def test_get_ruleset_context_custom_returns_empty():
    assert get_ruleset_context("custom") == {}


def test_build_ruleset_prompt_context_srd52():
    ctx = build_ruleset_prompt_context("srd-5.2")
    assert "D&D 5e" in ctx
    assert "CC-BY-4.0" in ctx
    assert "Artificer" in ctx
    assert "Blinded" in ctx


def test_build_ruleset_prompt_context_unknown_returns_empty():
    assert build_ruleset_prompt_context("unknown") == ""


def test_build_ruleset_prompt_context_custom_returns_empty():
    assert build_ruleset_prompt_context("custom") == ""


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def test_list_rulesets_no_auth():
    """GET /rulesets is public — no auth token required."""
    client = _client()
    resp = client.get("/rulesets")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "rulesets" in data
    ids = [r["id"] for r in data["rulesets"]]
    assert "srd-5.2" in ids
    assert "custom" in ids


def test_list_rulesets_srd_entry_has_license():
    client = _client()
    resp = client.get("/rulesets")
    assert resp.status_code == 200
    rulesets = resp.json()["rulesets"]
    srd_entry = next(r for r in rulesets if r["id"] == "srd-5.2")
    assert srd_entry["license"] == "CC-BY-4.0"
    assert "D&D 5e" in srd_entry["display"]


def test_get_ruleset_srd52_requires_auth():
    client = _client()
    resp = client.get("/rulesets/srd-5.2")
    assert resp.status_code == 401, resp.text


def test_get_ruleset_srd52_with_auth():
    client = _client()
    user = _ensure_user("srd-test-user@example.com")
    token = create_access_token(user.email or "")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/rulesets/srd-5.2", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ruleset"]["id"] == "srd-5.2"
    assert "data" in data
    assert "classes" in data["data"]
    assert "conditions" in data["data"]
    assert "skills" in data["data"]
    assert data["data"]["attribution"] is not None


def test_get_ruleset_not_found():
    client = _client()
    user = _ensure_user("srd-test-user@example.com")
    token = create_access_token(user.email or "")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/rulesets/nonexistent-system", headers=headers)
    assert resp.status_code == 404, resp.text


def test_get_ruleset_custom_returns_empty_data():
    client = _client()
    user = _ensure_user("srd-test-user@example.com")
    token = create_access_token(user.email or "")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/rulesets/custom", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["data"] == {}
