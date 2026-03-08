"""Tests for the character creation wizard config endpoint."""

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.auth import create_access_token


def _client() -> TestClient:
    return TestClient(main.app)


def _ensure_user(email: str) -> None:
    existing = db.get_user_by_identifier(email)
    if existing:
        if not existing.verified:
            db.verify_user(email, existing.verification_token or "")
        return
    user = db.create_user(
        email=email,
        password="secret",
        username=email.split("@")[0],
        profile={"name": email.split("@")[0], "email": email},
    )
    db.verify_user(email, user.verification_token)


def test_wizard_config_returns_systems():
    client = _client()
    res = client.get("/characters/wizard/config")
    assert res.status_code == 200, res.text
    data = res.json()
    assert "systems" in data
    systems = data["systems"]
    assert isinstance(systems, list)
    assert len(systems) > 0


def test_wizard_config_system_structure():
    """Each system entry should have the expected keys."""
    client = _client()
    res = client.get("/characters/wizard/config")
    data = res.json()
    required_keys = {
        "name", "publisher", "classes", "ability_scores",
        "standard_array", "point_buy_budget", "point_buy_min",
        "point_buy_max", "questions",
    }
    for system in data["systems"]:
        missing = required_keys - set(system.keys())
        assert not missing, f"System '{system.get('name')}' missing keys: {missing}"


def test_wizard_config_includes_dnd5e():
    """D&D 5e should be present and have correct classes."""
    client = _client()
    res = client.get("/characters/wizard/config")
    data = res.json()
    dnd5e = next((s for s in data["systems"] if s["name"] == "D&D 5e"), None)
    assert dnd5e is not None, "D&D 5e system not found in wizard config"
    assert "Fighter" in dnd5e["classes"]
    assert "Rogue" in dnd5e["classes"]
    assert "Wizard" in dnd5e["classes"]


def test_wizard_config_dnd5e_standard_array():
    """D&D 5e standard array should be [15, 14, 13, 12, 10, 8]."""
    client = _client()
    res = client.get("/characters/wizard/config")
    data = res.json()
    dnd5e = next(s for s in data["systems"] if s["name"] == "D&D 5e")
    assert dnd5e["standard_array"] == [15, 14, 13, 12, 10, 8]


def test_wizard_config_dnd5e_ability_scores():
    """D&D 5e ability scores should have the standard six attributes."""
    client = _client()
    res = client.get("/characters/wizard/config")
    data = res.json()
    dnd5e = next(s for s in data["systems"] if s["name"] == "D&D 5e")
    keys = {score["key"] for score in dnd5e["ability_scores"]}
    assert keys == {"str", "dex", "con", "int", "wis", "cha"}


def test_wizard_config_dnd5e_questions():
    """D&D 5e should have questionnaire questions with choices."""
    client = _client()
    res = client.get("/characters/wizard/config")
    data = res.json()
    dnd5e = next(s for s in data["systems"] if s["name"] == "D&D 5e")
    questions = dnd5e["questions"]
    assert len(questions) >= 3, "Expected at least 3 questions for D&D 5e"
    for question in questions:
        assert "id" in question
        assert "text" in question
        assert "choices" in question
        assert len(question["choices"]) >= 2, "Each question should have at least 2 choices"
        for choice in question["choices"]:
            assert "id" in choice
            assert "text" in choice
            assert "skills" in choice
            assert "narrative" in choice


def test_wizard_config_question_choices_have_skills():
    """Every question choice should map to at least one skill."""
    client = _client()
    res = client.get("/characters/wizard/config")
    data = res.json()
    for system in data["systems"]:
        for question in system.get("questions", []):
            for choice in question.get("choices", []):
                assert len(choice.get("skills", [])) > 0, (
                    f"Choice '{choice.get('id')}' in question '{question.get('id')}' "
                    f"of system '{system.get('name')}' has no skills"
                )


def test_wizard_config_does_not_require_auth():
    """The wizard config endpoint should be publicly accessible (no auth needed)."""
    client = _client()
    res = client.get("/characters/wizard/config")
    assert res.status_code == 200


def test_create_character_from_wizard_data():
    """Creating a character with wizard-produced sheet data should succeed."""
    client = _client()
    email = "wizard-creator@example.com"
    _ensure_user(email)
    token = create_access_token(email)
    auth_headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/characters",
        headers=auth_headers,
        json={
            "name": "Thalion Swiftblade",
            "level": 3,
            "class_name": "Rogue",
            "sheet": {
                "game_system": "D&D 5e",
                "stats": {"str": 10, "dex": 15, "con": 13, "int": 12, "wis": 8, "cha": 14},
                "skills": [
                    {"name": "Stealth"},
                    {"name": "Deception"},
                    {"name": "Perception"},
                ],
                "background": "Criminal",
                "languages": "Common, Thieves' Cant",
                "backstory": "Raised in the slums, cunning has always been your greatest weapon.",
                "created_via": "wizard",
            },
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["character"]["name"] == "Thalion Swiftblade"
    assert data["character"]["level"] == 3
    assert data["character"]["class_name"] == "Rogue"
    assert data["character"]["sheet"]["game_system"] == "D&D 5e"
    assert data["character"]["sheet"]["created_via"] == "wizard"
    assert data["character"]["sheet"]["background"] == "Criminal"
