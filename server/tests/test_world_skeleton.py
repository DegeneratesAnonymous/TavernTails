import json

from fastapi.testclient import TestClient
from sqlmodel import Session, select

import server.main as main
from server import db
from server.agents import world_skeleton
from server.agents.campaign_card import read_campaign_card
from server.agents.premise_seed import reveals_secret
from server.auth import create_access_token
from server.db import CampaignEntity, CampaignHook

TRUTH = {
    "thread_name": "The Dark Lamp",
    "visible_problem": "The lighthouse lamp went dark and the keeper is missing.",
    "hidden_truth": "Harbor master Dace sold the keeper to smugglers so their ships could land unseen.",
    "who_benefits": "Dace (harbor master)",
    "first_clue": "Fresh tar on the lighthouse stair that no keeper would track in.",
    "stakes": "Ships wreck on the reef every dark night.",
}
FACTIONS = {"factions": [
    {"name": "Salt Syndicate", "wants": "Land cargo unseen.", "plan": "Bribe the harbor office.", "if_ignored": "Burn the lamp oil stores."},
    {"name": "Harbor Office", "wants": "Keep the port taxed.", "plan": "Blame the keeper.", "if_ignored": "Close the docks."},
]}
NPCS = {"npcs": [
    {"name": "Ilsa Dace", "role": "harbor master", "faction": "harbor office", "wants": "Stay rich.", "secret": "She sold the keeper.", "knows": "The smugglers' schedule."},
    {"name": "Tomas Reed", "role": "dock boy", "faction": "", "wants": "Find his sister.", "secret": "He stole the lamp key.", "knows": "Who climbed the stair."},
    {"name": "Salt Syndicate", "role": "dup", "faction": "", "wants": "x", "secret": "y", "knows": "z"},
]}
CLOCK = {"title": "Wreckers' Moon", "steps": ["A ship runs aground.", "The town blames the keeper.", "The smugglers seize the lighthouse."], "deadline": "the third night"}
SEED = {
    "starting_location": "Gull Steps lighthouse", "location_type": "lighthouse",
    "location_identity": "A harbor lighthouse whose lamp has gone dark over the town.",
    "inciting_event": "The lighthouse keeper vanished and the harbor lamp is dark.",
    "named_npc_or_visible_threat": "Tomas Reed (dock boy)", "immediate_problem": "The lamp is dark.",
    "specific_stakes": "Ships will wreck.", "first_clue_or_question": "Who tracked tar up the stair?",
    "player_decision": "Climb the stair, question Tomas, or check the docks.",
}


def _model(answers):
    """Answer each skeleton prompt by its system message."""
    def call(messages, **kwargs):
        system = messages[0]["content"]
        for marker, answer in answers.items():
            if marker in system:
                return json.dumps(answer) if isinstance(answer, dict) else answer
        return None
    return call


def _full_model(**overrides):
    # Overrides go first: the card prompt also mentions "factions".
    answers = {**overrides}
    for marker, answer in {'"thread_name"': TRUTH, '"factions"': FACTIONS, '"npcs"': NPCS, '"deadline"': CLOCK, "opening situation": SEED}.items():
        answers.setdefault(marker, answer)
    return _model(answers)


def _user(email: str) -> db.User:
    user = db.get_user_by_identifier(email)
    if user is None:
        user = db.create_user(email=email, password="secret", username=email.split("@")[0])
        assert user.verification_token
        db.verify_user(email, user.verification_token)
        user = db.get_user_by_identifier(email)
    assert user is not None
    return user


def _campaign(email: str, **settings) -> db.Campaign:
    user = _user(email)
    assert user.id is not None
    camp = db.create_campaign(owner_id=user.id, name="Dark Lamp", description="")
    db.set_campaign_metadata_keys(str(camp.id), user.id, {
        "settings": {
            "genre": "mystery", "tone": "grim",
            "setting_summary": "A grim harbor town where the lighthouse keeper vanished and the lamp went dark.",
            **settings,
        },
        "campaign_card": {
            "text": "A grim harbor town where the keeper Maren Vey vanished. The Tidewardens run the docks.",
            "people": [{"name": "Maren Vey"}], "factions": [{"name": "Tidewardens"}],
        },
    })
    world_skeleton.init_state(str(camp.id))
    return camp


def _entities(campaign_id: str) -> list[CampaignEntity]:
    with Session(db.engine) as s:
        return list(s.exec(select(CampaignEntity).where(CampaignEntity.campaign_id == campaign_id)).all())


def test_skeleton_writes_gm_only_memory_for_every_piece():
    camp = _campaign("skeleton-full@example.com", opening_trouble="The lamp went dark")
    state = world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model())
    assert state["status"] == "ready"
    entities = _entities(str(camp.id))
    assert all(e.visibility == "gm_only" and world_skeleton.TAG in e.tags for e in entities)
    thread = next(e for e in entities if e.entity_type == "story_thread")
    # The secret is GM notes; the clue-facing field only says what the party can see.
    assert thread.data["gm_notes"] == TRUTH["hidden_truth"]
    assert thread.data["current_situation"] == TRUTH["visible_problem"]
    assert thread.data["ticking_clock"] == "the third night"
    factions = {e.name: e.data for e in entities if e.entity_type == "faction"}
    assert factions["Tidewardens"]["provenance"] == "user"  # the player's faction exists even if the model forgot it
    assert factions["Salt Syndicate"]["provenance"] == "generated_provisional"
    npcs = {e.name: e.data for e in entities if e.entity_type == "npc"}
    assert set(npcs) == {"Maren Vey", "Ilsa Dace", "Tomas Reed"}  # a faction name is not a person
    assert npcs["Ilsa Dace"]["faction_affiliations"] == ["Harbor Office"]
    assert npcs["Ilsa Dace"]["secrets"] == ["She sold the keeper."]
    with Session(db.engine) as s:
        hooks = s.exec(select(CampaignHook).where(CampaignHook.campaign_id == str(camp.id))).all()
    assert [(h.hook_type, h.deadline) for h in hooks] == [("ticking_clock", "the third night")]
    assert state["opening_seed"]["generated_by"] == "premise_seed"


def test_failed_pieces_stay_open_and_retry_fills_only_them():
    camp = _campaign("skeleton-partial@example.com")
    state = world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model(**{'"npcs"': "not json"}))
    assert state["status"] == "partial"
    assert state["pieces"]["npcs"] == {"status": "failed", "reason": "unparseable"}
    before = len(_entities(str(camp.id)))

    state = world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model())
    assert state["status"] == "ready"
    after = _entities(str(camp.id))
    assert len(after) == before + 3  # only the NPCs were added; the truth and factions were not duplicated


def test_truth_must_match_the_players_opening_trouble():
    assert world_skeleton.validate_truth(TRUTH, opening_trouble="The bridge collapsed overnight") is None
    assert world_skeleton.validate_truth(TRUTH, opening_trouble="The lamp went dark") is not None
    restated = {**TRUTH, "hidden_truth": TRUTH["visible_problem"]}
    assert world_skeleton.validate_truth(restated) is None


def test_contents_are_hidden_unless_shown_or_dm():
    camp = _campaign("skeleton-view@example.com")
    world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model(**{'"deadline"': "nope"}))
    state = db.get_campaign_by_id(str(camp.id)).metadata_json["world_skeleton"]
    hidden = world_skeleton.public_view(state)
    assert "data" not in hidden["pieces"]["truth"]
    assert hidden["pieces"]["clock"]["status"] == "failed"
    # Contents are read back from the GM-only rows.
    assert world_skeleton.public_view(state, reveal=True)["pieces"]["truth"]["data"] == TRUTH
    shown = world_skeleton.public_view({**state, "visibility": "show"})["pieces"]
    assert shown["npcs"]["data"][1] == {
        "name": "Ilsa Dace", "role": "harbor master", "wants": "Stay rich.", "secret": "She sold the keeper.",
        "knows": "The smugglers' schedule.", "faction": "Harbor Office",
    }
    assert "data" not in shown["clock"]


def test_secrets_never_reach_campaign_metadata():
    """GET /campaigns returns metadata whole, so the secrets must live only in GM-only rows."""
    camp = _campaign("skeleton-metadata@example.com")
    world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model())
    stored = json.dumps(db.get_campaign_by_id(str(camp.id)).metadata_json)
    for secret in (TRUTH["hidden_truth"], "She sold the keeper.", "Wreckers' Moon", "Land cargo unseen."):
        assert secret not in stored
    user = db.get_user_by_identifier("skeleton-metadata@example.com")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}
    listing = TestClient(main.app).get("/campaigns", headers=headers).text
    assert TRUTH["hidden_truth"] not in listing and "She sold the keeper." not in listing
    assert world_skeleton.hidden_truth(db.get_campaign_by_id(str(camp.id))) == TRUTH


def test_a_piece_is_ready_only_once_its_rows_are_saved(monkeypatch):
    camp = _campaign("skeleton-persist@example.com")
    original = world_skeleton._persist

    def flaky(campaign, piece, value, **kwargs):
        if piece == "factions":
            raise RuntimeError("database went away")
        return original(campaign, piece, value, **kwargs)

    monkeypatch.setattr(world_skeleton, "_persist", flaky)
    state = world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model())
    assert state["pieces"]["factions"] == {"status": "failed", "reason": "persist_error"}
    assert not [e for e in _entities(str(camp.id)) if e.entity_type == "faction"]

    monkeypatch.setattr(world_skeleton, "_persist", original)
    state = world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model())
    assert state["pieces"]["factions"]["status"] == "ready"
    assert {e.name for e in _entities(str(camp.id)) if e.entity_type == "faction"} == {"Tidewardens", "Salt Syndicate", "Harbor Office"}


def test_names_only_in_setting_notes_keep_imported_provenance():
    camp = _campaign("skeleton-lore@example.com")
    owner = db.get_user_by_identifier("skeleton-lore@example.com")
    meta = dict(db.get_campaign_by_id(str(camp.id)).metadata_json)
    meta["campaign_card"] = {**meta["campaign_card"], "factions": [{"name": "Tidewardens"}, {"name": "Salt Syndicate"}]}
    meta["imported_lore"] = ["The Salt Syndicate smuggles brandy past the reef."]
    db.set_campaign_metadata_keys(str(camp.id), owner.id, meta)
    world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model())
    factions = {e.name: e.data["provenance"] for e in _entities(str(camp.id)) if e.entity_type == "faction"}
    assert factions["Tidewardens"] == "user"
    assert factions["Salt Syndicate"] == "imported"
    assert factions["Harbor Office"] == "generated_provisional"


def test_prepared_opening_seed_is_used_once():
    camp = _campaign("skeleton-seed@example.com")
    world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model())
    first = world_skeleton.take_opening_seed(db.get_campaign_by_id(str(camp.id)))
    assert first and first["starting_location"] == "Gull Steps lighthouse"
    assert world_skeleton.take_opening_seed(db.get_campaign_by_id(str(camp.id))) is None


def test_seed_that_states_the_secret_is_rejected():
    premise = "A grim harbor town where the lighthouse keeper vanished."
    leaky = {**SEED, "immediate_problem": "Harbor master Dace sold the keeper to smugglers."}
    assert reveals_secret(leaky, TRUTH, premise)
    assert not reveals_secret(SEED, TRUTH, premise)


def test_card_endpoint_and_card_creation_start_the_skeleton(monkeypatch):
    user = _user("card-flow@example.com")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}
    client = TestClient(main.app)
    import server.steward_llm as steward_llm

    card_answer = json.dumps({"name": "The Dark Lamp", "genre": "mystery", "tone": "grim", "factions": ["Tidewardens"]})
    model = _full_model(**{"campaign card": card_answer})
    monkeypatch.setattr(steward_llm, "chat_complete", model)

    text = "A grim harbor town where the lighthouse keeper vanished. The Tidewardens run the docks."
    res = client.post("/campaigns/card", headers=headers, json={"text": text, "starter": {"seed_id": "cozy-village-mystery"}})
    assert res.status_code == 200
    card = res.json()["card"]
    assert card["fields"]["name"]["value"] == "The Dark Lamp"
    assert card["derived"]["creation_posture"] == "guided_builder"

    res = client.post("/campaigns", headers=headers, json={
        "name": "", "card": card, "create_session": False, "owner_role": "dm",
        "follow_up_answers": {"opening_trouble": "The lamp went dark last night"},
        "world_visibility": "surprise",
    })
    assert res.status_code == 201, res.text
    campaign = res.json()["campaign"]
    assert campaign["name"] == "The Dark Lamp"
    meta = db.get_campaign_by_id(campaign["id"]).metadata_json
    assert meta["settings"]["opening_trouble"] == "The lamp went dark last night"
    assert meta["campaign_card"]["fields"]["opening_trouble"]["status"] == "said"
    assert meta["variables"]["factions"] == [{"name": "Tidewardens"}]

    # TestClient runs background tasks before returning, so the skeleton is already built.
    world = client.get(f"/campaigns/{campaign['id']}/world", headers=headers).json()["world"]
    assert world["status"] == "ready"
    assert world["pieces"]["truth"]["data"]["hidden_truth"] == TRUTH["hidden_truth"]  # owner seated as DM

    other = _user("card-flow-other@example.com")
    denied = client.get(f"/campaigns/{campaign['id']}/world", headers={"Authorization": f"Bearer {create_access_token(other.email or '')}"})
    assert denied.status_code == 403


def test_player_owner_sees_only_status_until_they_choose_show(monkeypatch):
    user = _user("card-flow-player@example.com")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}
    client = TestClient(main.app)
    import server.steward_llm as steward_llm

    monkeypatch.setattr(steward_llm, "chat_complete", _full_model())
    card = read_campaign_card("A grim harbor town where the lighthouse keeper vanished.", complete=lambda *a, **k: None)
    res = client.post("/campaigns", headers=headers, json={"name": "Lamp", "card": card, "create_session": False})
    cid = res.json()["campaign"]["id"]
    world = client.get(f"/campaigns/{cid}/world", headers=headers).json()["world"]
    assert world["status"] == "ready" and "data" not in world["pieces"]["truth"]

    shown = client.post(f"/campaigns/{cid}/world", headers=headers, json={"visibility": "show"}).json()["world"]
    assert shown["pieces"]["truth"]["data"]["thread_name"] == "The Dark Lamp"
    bad = client.post(f"/campaigns/{cid}/world", headers=headers, json={"visibility": "everyone"})
    assert bad.status_code == 422


def test_campaigns_created_without_a_card_do_not_build_a_world():
    user = _user("no-card@example.com")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}
    client = TestClient(main.app)
    res = client.post("/campaigns", headers=headers, json={"name": "Classic", "create_session": False})
    cid = res.json()["campaign"]["id"]
    assert client.get(f"/campaigns/{cid}/world", headers=headers).json()["world"]["status"] == "not_started"


def test_a_visibility_change_during_the_job_survives_its_saves():
    camp = _campaign("skeleton-race@example.com")
    base = _full_model()

    def model(messages, **kwargs):
        if '"thread_name"' in messages[0]["content"]:
            # The owner presses "Show me the world" while the truth call is running.
            fresh = db.get_campaign_by_id(str(camp.id))
            state = dict(fresh.metadata_json["world_skeleton"])
            db.set_campaign_metadata_keys(str(camp.id), fresh.owner_id, {"world_skeleton": {**state, "visibility": "show"}})
        return base(messages, **kwargs)

    world_skeleton.generate_world_skeleton(str(camp.id), complete=model)
    stored = db.get_campaign_by_id(str(camp.id)).metadata_json["world_skeleton"]
    assert stored["visibility"] == "show"
    assert stored["status"] == "ready"


def test_a_session_that_opened_first_closes_the_seed_slot():
    camp = _campaign("skeleton-seed-race@example.com")
    assert world_skeleton.take_opening_seed(db.get_campaign_by_id(str(camp.id))) is None  # questionnaire built early
    asked: list[str] = []
    base = _full_model()

    def model(messages, **kwargs):
        asked.append(messages[0]["content"])
        return base(messages, **kwargs)

    state = world_skeleton.generate_world_skeleton(str(camp.id), complete=model)
    assert not any("opening situation" in system for system in asked)  # no seed is prepared for a later session
    assert "opening_seed" not in state or not db.get_campaign_by_id(str(camp.id)).metadata_json["world_skeleton"].get("opening_seed")
    assert world_skeleton.take_opening_seed(db.get_campaign_by_id(str(camp.id))) is None


def test_activity_is_judged_by_age_not_by_process():
    from datetime import timedelta

    recent = (world_skeleton._now() - timedelta(minutes=2)).isoformat()
    old = (world_skeleton._now() - timedelta(minutes=40)).isoformat()
    assert world_skeleton.is_active("elsewhere", {"status": "running", "started_at": recent})
    assert not world_skeleton.is_active("elsewhere", {"status": "running", "started_at": old})
    assert world_skeleton.is_active("elsewhere", {"status": "pending", "requested_at": recent})
    assert not world_skeleton.is_active("elsewhere", {"status": "ready", "started_at": recent})
    assert not world_skeleton.is_active("elsewhere", {"status": "pending"})


def test_retry_keeps_finished_pieces():
    user = _user("skeleton-retry@example.com")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}
    camp = _campaign("skeleton-retry@example.com")
    world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model(**{'"deadline"': "nope"}))
    client = TestClient(main.app)
    import server.steward_llm as steward_llm

    asked: list[str] = []

    def model(messages, **kwargs):
        asked.append(messages[0]["content"])
        return _full_model()(messages, **kwargs)

    steward_llm_original = steward_llm.chat_complete
    steward_llm.chat_complete = model
    try:
        queued = client.post(f"/campaigns/{camp.id}/world", headers=headers, json={"retry": True}).json()["world"]
    finally:
        steward_llm.chat_complete = steward_llm_original
    assert queued["status"] == "pending"  # the response is sent before the background job runs
    world = client.get(f"/campaigns/{camp.id}/world", headers=headers).json()["world"]
    assert world["status"] == "ready"
    assert len(asked) == 1 and '"deadline"' in asked[0]  # only the clock was asked for again


def test_only_the_owner_can_lift_the_surprise():
    owner = _user("skeleton-owner@example.com")
    gm = _user("skeleton-gm@example.com")
    camp = _campaign("skeleton-owner@example.com")
    with Session(db.engine) as s:
        row = s.get(db.Campaign, camp.id)
        row.gm_user_id = gm.id
        s.add(row)
        s.commit()
    client = TestClient(main.app)
    gm_headers = {"Authorization": f"Bearer {create_access_token(gm.email or '')}"}
    denied = client.post(f"/campaigns/{camp.id}/world", headers=gm_headers, json={"visibility": "show"})
    assert denied.status_code == 403
    assert db.get_campaign_by_id(str(camp.id)).metadata_json["world_skeleton"]["visibility"] == "surprise"
    owner_headers = {"Authorization": f"Bearer {create_access_token(owner.email or '')}"}
    assert client.post(f"/campaigns/{camp.id}/world", headers=owner_headers, json={"visibility": "show"}).status_code == 200


def test_a_malformed_card_is_a_422_not_a_500():
    user = _user("card-malformed@example.com")
    headers = {"Authorization": f"Bearer {create_access_token(user.email or '')}"}
    client = TestClient(main.app)
    for card in (
        {"fields": {"starting_level": {"value": "three", "status": "said"}}},
        {"fields": {"pacing": {"value": "glacial", "status": "guessed"}}},
        {"fields": {"tone": {"value": "grim", "status": "certain"}}},
        {"fields": "not a mapping"},
    ):
        res = client.post("/campaigns", headers=headers, json={"name": "Bad", "card": card, "create_session": False})
        assert res.status_code == 422, (card, res.text)


def test_a_surprised_player_owner_cannot_read_the_world_through_memory_tools():
    owner = _user("skeleton-memory@example.com")
    camp = _campaign("skeleton-memory@example.com")
    db.set_campaign_metadata_keys(str(camp.id), owner.id, {"owner_participation": {"role": "player", "character_id": None}})
    world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model())
    client = TestClient(main.app)
    headers = {"Authorization": f"Bearer {create_access_token(owner.email or '')}"}
    base = f"/memory/{camp.id}"

    entities = client.get(f"{base}/entities", headers=headers)
    assert entities.status_code == 200 and entities.json() == []
    thread = next(e for e in _entities(str(camp.id)) if e.entity_type == "story_thread")
    assert client.get(f"{base}/entities/{thread.id}", headers=headers).status_code == 404
    assert client.get(f"{base}/changelog/{thread.id}", headers=headers).status_code == 404
    assert client.put(f"{base}/entities/{thread.id}", headers=headers, json={"name": "x"}).status_code == 404
    assert TRUTH["hidden_truth"] not in client.get(f"{base}/changelog", headers=headers).text
    assert client.get(f"{base}/hooks", headers=headers).json() == []
    assert client.post(f"{base}/context", headers=headers, json={}).status_code == 403
    assert client.get(f"{base}/next-actions", headers=headers).status_code == 403

    # Once the owner chooses to see the world, the GM tools work as before.
    client.post(f"/campaigns/{camp.id}/world", headers=headers, json={"visibility": "show"})
    assert len(client.get(f"{base}/entities", headers=headers).json()) == len(_entities(str(camp.id)))
    assert client.get(f"{base}/next-actions", headers=headers).status_code == 200


def test_the_truth_must_cover_the_authored_trouble():
    bridge = {**TRUTH, "thread_name": "Murder at the Crossing",
              "visible_problem": "A merchant lies dead near the bridge."}
    assert world_skeleton.validate_truth(bridge, opening_trouble="The bridge collapsed overnight") is None
    collapse = {**bridge, "visible_problem": "The bridge collapsed overnight, stranding the caravan."}
    assert world_skeleton.validate_truth(collapse, opening_trouble="The bridge collapsed overnight") is not None


def test_failed_pieces_say_why():
    camp = _campaign("skeleton-reason@example.com")
    world_skeleton.generate_world_skeleton(str(camp.id), complete=_full_model(**{'"deadline"': "not json"}))
    view = world_skeleton.public_view(db.get_campaign_by_id(str(camp.id)).metadata_json["world_skeleton"])
    assert view["pieces"]["clock"] == {"status": "failed", "reason": "unparseable"}
    assert "reason" not in view["pieces"]["truth"]


def test_the_untold_seed_retry_is_still_checked_for_the_secret():
    camp = _campaign("skeleton-seed-leak@example.com")
    leaky = {**SEED, "immediate_problem": "Harbor master Dace sold the keeper to smugglers."}
    seen_hints: list[bool] = []

    def model(messages, **kwargs):
        if "opening situation" in messages[0]["content"]:
            seen_hints.append("GM-only background" in messages[1]["content"])
            return json.dumps(leaky)
        return _full_model()(messages, **kwargs)

    state = world_skeleton.generate_world_skeleton(str(camp.id), complete=model)
    assert seen_hints == [True, False]  # told, then retried without the hint
    assert not state.get("opening_seed")  # both answers stated the secret, so neither became the seed
