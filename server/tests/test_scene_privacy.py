"""GM-only planning and NPC secrets stay out of everything sent to clients."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import sessions as sessions_module
from server.agents.scene_privacy import player_view
from server.auth import create_access_token

SCENE = {
    "id": "s1", "narrative_body": "Ada Reed sets down the watch.",
    "campaign_storyboard": {"twist": "Ada is the thief"}, "arc_plan": {"reveal": "scene 9"},
    "scene_director_data": {
        "hidden_pressure": "The guild will burn the shop at dawn.",
        "primary_npc": {"name": "Ada Reed", "role": "clockmaker", "what_they_know": "She sold the key.",
                        "what_they_want": "To hide it.", "secrets": ["the key"]},
        "secondary_entities": [{"name": "Boy", "what_they_know": "He saw her."}],
        "player_visible_clues": ["a stopped watch"],
    },
}


def test_player_view_removes_gm_only_fields_and_keeps_the_rest():
    view = player_view(SCENE)
    text = json.dumps(view)
    for secret in ("Ada is the thief", "scene 9", "burn the shop", "sold the key", "To hide it", "He saw her"):
        assert secret not in text
    assert view["narrative_body"] == SCENE["narrative_body"]
    assert view["scene_director_data"]["primary_npc"]["name"] == "Ada Reed"
    assert view["scene_director_data"]["player_visible_clues"] == ["a stopped watch"]
    assert "hidden_pressure" in SCENE["scene_director_data"], "the original scene must not be modified"


def test_player_view_passes_non_scenes_through():
    assert player_view(None) is None
    assert player_view([1]) == [1]


def test_scene_file_endpoint_does_not_send_gm_secrets():
    email = "privacy-owner@example.com"
    if not db.get_user_by_identifier(email):
        user = db.create_user(email=email, password="secret", username="privacy-owner", profile={"name": "p", "email": email})
        db.verify_user(email, user.verification_token)
    sid, _ = sessions_module.create_session_folder("Privacy", email)
    (sessions_module.BASE / sid / "scene.json").write_text(json.dumps(SCENE))
    client = TestClient(main.app)
    res = client.get(f"/sessions/{sid}/file/scene.json", headers={"Authorization": f"Bearer {create_access_token(email)}"})
    assert res.status_code == 200
    assert "Ada is the thief" not in res.text and "sold the key" not in res.text and "burn the shop" not in res.text
    assert "Ada Reed" in res.text
    # the AI GM still has the full scene on disk
    assert "sold the key" in (sessions_module.BASE / sid / "scene.json").read_text()
