"""Opt-in (`--llm`): a world and a backstory, carried through the story with a real model.

World text -> campaign card -> world skeleton -> character with a backstory kept for the campaign ->
opening questions that offer it -> start -> the character's thread in memory -> a few more scenes.
Slow (several minutes). It prints the scenes for a human to read; the assertions are the mechanical contract.
"""
import json
import re

import pytest
from fastapi.testclient import TestClient

from server import db, main
from server.agents import continuity, thread_weaver
from server.auth import create_access_token

WORLD = (
    "Saltmere is a grim harbour town where the grain stores keep catching fire. The Salt Court controls the grain and "
    "the Reed Guild keeps the ferries free. The places that matter are the Ashen Market and Low Dock. "
    "The story opens in the Ashen Market. Supplies are failing and neighbours are turning on each other."
)


@pytest.mark.llm
def test_a_backstory_is_woven_into_the_story():
    email = "live-lifepath@example.com"
    user = db.get_user_by_identifier(email) or db.create_user(email=email, username="livelp", password="secret", profile={})
    if not user.verified:
        db.verify_user(email, user.verification_token or "")
    user = db.get_user_by_identifier(email)
    client = TestClient(main.app)
    client.headers["Authorization"] = f"Bearer {create_access_token(email)}"
    mira = db.create_character(owner_id=user.id, name="Mira Vale", level=1, class_name="Rogue", sheet={})

    card = client.post("/campaigns/card", json={"text": WORLD}).json()["card"]
    created = client.post("/campaigns", json={
        "name": "Saltmere", "card": card, "owner_role": "player", "owner_character_id": mira.id, "create_session": True, "generate_world": True,
    })
    assert created.status_code == 201, created.text
    assert not created.json().get("warnings"), created.json()["warnings"]
    cid = created.json()["campaign"]["id"]
    sid = created.json()["campaign"]["sessions"][0]["id"]

    kept = client.post(f"/lifepath/campaigns/{cid}/characters/{mira.id}", json={
        "backstory": "Mira grew up in the Ashen Market and lost her mentor to the Salt Court.",
        "goals": [{"term": "long", "text": "bring the Salt Court to account", "because": "they let her street starve"},
                  {"term": "short", "text": "find who burned the granary"}],
        "allies": ["Tam, a ferryman"], "rivals": ["a magistrate who wants her quiet"], "link": {"kind": "faction", "name": "Salt Court"},
    })
    assert kept.status_code == 200

    setup = client.get(f"/sessions/{sid}/opening-setup").json()
    options = [o["value"] for q in setup["questionnaire"]["questions"] for o in q["options"] if o["id"] == "backstory"]
    assert "I came to find who burned the granary" in options, options
    assert client.post(f"/sessions/{sid}/opening-setup/skip").status_code == 200

    started = client.post(f"/sessions/{sid}/start", json={})
    assert started.status_code == 200, started.text
    rows = thread_weaver.b_plot_rows(cid)
    assert len(rows) == 1 and rows[0].visibility == "gm_only" and rows[0].data["plot"] == "B"
    print("\nTHREAD:", json.dumps(rows[0].data, indent=1))
    scenes = [started.json()["scene"]["narrative_body"]]
    for _ in range(3):
        res = client.post(f"/sessions/{sid}/advance-scene", json={})
        assert res.status_code == 200, res.text
        scenes.append(res.json()["scene"]["narrative_body"])
    for i, text in enumerate(scenes):
        print(f"\n--- scene {i} ---\n{text}")
        assert "?" not in text.split("\n\n")[0] or i > 0
    names = continuity.locked_names(db.get_campaign_by_id(cid))
    for text in scenes:
        assert continuity.name_drifts(text, names) == [], (names, text)
    assert all(continuity.repeated_wording(scenes[i], scenes[:i]) < 0.35 for i in range(1, len(scenes)))
    assert not re.search(r"\bthe party\b", scenes[0], re.I)
