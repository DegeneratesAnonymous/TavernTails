import json
import os
import re

import pytest
from fastapi.testclient import TestClient

from server import db, main
from server.auth import create_access_token

PREMISES = {
    "asylum": ("A county asylum where the patients' records rewrite themselves and a ward was bricked up years ago.", {"genre": "horror", "tone": "dark"}),
    "clocks": ("At Alderbrook village, every clock stopped at breakfast. Clockmaker Ada Reed has a stopped brass pocket watch on her workbench. Find the cause without frightening the neighbors.", {"genre": "mystery", "tone": "cozy"}),
}


def _campaign(email, name, premise, prefs):
    user = db.get_user_by_identifier(email)
    if not user:
        user = db.create_user(email=email, username=email.split("@")[0], password="secret", profile={})
    if not user.verified:
        db.verify_user(email, user.verification_token or "")
    client = TestClient(main.app)
    client.headers["Authorization"] = f"Bearer {create_access_token(email)}"
    created = client.post("/campaigns", json={"name": name, "description": premise, "create_session": True,
                                              "preferences": {**prefs, "setting_summary": premise}})
    assert created.status_code == 201, created.text
    sid = created.json()["campaign"]["sessions"][0]["id"]
    assert client.post(f"/sessions/{sid}/opening-setup/skip").status_code == 200
    return client, sid


@pytest.mark.llm
@pytest.mark.parametrize("key", list(PREMISES))
def test_live_opening(key, tmp_path):
    premise, prefs = PREMISES[key]
    client, sid = _campaign(f"live-{key}@example.com", f"Live {key}", premise, prefs)
    resp = client.post(f"/sessions/{sid}/start", json={})
    assert resp.status_code == 200, resp.text
    scene = resp.json()["scene"]
    (tmp_path / f"opening-{key}.json").write_text(json.dumps(scene, indent=2, default=str))  # for a human to read
    body = scene["narrative_body"]
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    # The scene reads as one piece of fiction: the prompt is not in the story, the player's setup answers are not
    # quoted back, no list of options is written into it, and nothing is stacked on after the closing beat.
    assert not re.search(r"what (?:does|do) [^?]{1,60}\?", body, re.I), body
    assert "?." not in body and ". ." not in body and "!." not in body, body
    assert not re.search(r"\bcan [^.]{0,120},[^.]{0,80}, or\b", body), body
    assert 'I came' not in body and 'My ' not in body.split("\n\n")[0], body
    assert "the player" not in body.lower(), body
    assert len(paragraphs) >= 3, body
    # The summary beside it only names people the story names.
    view = scene["scene_view"]
    assert view["place"] and all(p["name"].split()[0].lower() in body.lower() for p in view["present"]), (view, body)
