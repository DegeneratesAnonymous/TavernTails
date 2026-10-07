from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.agents import opening_setup as opening_setup_module
from server.agents import sessions as sessions_module
from server.agents.opening_setup import (
    auto_generate_answers,
    build_campaign_brief,
    build_opening_scene_contract,
    generate_provisional_character_anchor,
    generate_questionnaire,
    naturalizeCharacterKnowledge,
    validate_campaign_brief,
    validate_first_scene_contract,
    validate_opening_anchor,
    validate_opening_scene_contract,
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


def _auth(email: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(email)}"}


def _create_campaign_session(client: TestClient, email: str, character_name: str = "Opening Tester") -> tuple[str, int]:
    user = _ensure_user(email)
    assert user.id is not None
    character = db.create_character(
        owner_id=user.id,
        name=character_name,
        level=3,
        class_name="Ranger",
        sheet={"backstory": "A careful scout who owes a debt to a missing archivist."},
    )
    response = client.post(
        "/campaigns",
        headers=_auth(email),
        json={
            "name": "Opening Anchor Test",
            "description": "A mystery in a glass harbor where missing envoys and broken signal mirrors point to sabotage.",
            "create_session": True,
            "owner_role": "player",
            "owner_character_id": character.id,
            "preferences": {
                "genre": "fantasy mystery",
                "tone": "tense",
                "setting_summary": "A glass harbor where signal mirrors fail and envoys vanish before dawn.",
            },
        },
    )
    assert response.status_code == 201, response.text
    session_id = str(response.json()["campaign"]["sessions"][0]["id"])
    return session_id, int(character.id)


def test_opening_setup_required_and_blocks_start_until_completed():
    client = _client()
    email = "opening-required@example.com"
    session_id, character_id = _create_campaign_session(client, email, "Anchor Scout")

    meta = client.get(f"/sessions/{session_id}/meta", headers=_auth(email)).json()
    assert meta["opening_setup"]["required"] is True
    assert meta["opening_setup"]["completed"] is False
    assert meta["members"][0]["character_id"] == character_id

    start = client.post(f"/sessions/{session_id}/start", headers=_auth(email), json={})
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["ok"] is False
    assert body["requires_opening_setup"] is True
    assert body["opening_setup_url"] == f"/sessions/{session_id}/opening-setup"

    scene = json.loads((Path(sessions_module.BASE) / session_id / "scene.json").read_text())
    assert scene["setup_pending"] is True
    assert scene["choices"] == []
    assert "Choose an approach to set the tone" not in scene["text"]


def test_questionnaire_is_campaign_specific_and_anchor_saves_custom_answers():
    client = _client()
    email = "opening-questionnaire@example.com"
    session_id, _character_id = _create_campaign_session(client, email, "Glass Scout")

    setup = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email))
    assert setup.status_code == 200, setup.text
    questionnaire = setup.json()["questionnaire"]
    questions = questionnaire["questions"]
    campaign_brief = questionnaire["campaign_brief"]
    assert 3 <= len(questions) <= 5
    assert {"arrival_reason", "personal_stake", "followed_complication", "fear_of_loss"}.issubset({q["id"] for q in questions})
    assert all(any(option["id"] == "ai_choose" for option in question["options"]) for question in questions)
    questionnaire_blob = json.dumps(questionnaire).lower()
    assert any(term in questionnaire_blob for term in ("glass", "harbor", "signal", "mirror"))
    assert "glass scout" in questionnaire_blob
    assert campaign_brief["title"] == "Opening Anchor Test"
    assert campaign_brief["location_name"]
    assert 1 <= len(" ".join(campaign_brief["brief_paragraphs"]).split()) <= 250
    assert "who is lying?" not in questionnaire_blob
    assert "as a ranger" not in questionnaire_blob
    assert all(question.get("helper_text") for question in questions)
    by_id = {question["id"]: question for question in questions}
    assert by_id["arrival_reason"]["question"] == "What brought Glass Scout here?"
    assert by_id["personal_stake"]["question"] == "Why does this matter to Glass Scout?"
    assert "before anyone else disturbs it" not in questionnaire_blob
    assert "very wrong" not in questionnaire_blob

    submit = client.post(
        f"/sessions/{session_id}/opening-setup",
        headers=_auth(email),
        json={
            "questionnaire_id": questionnaire["questionnaire_id"],
            "answers": [
                {
                    "question_id": "arrival_reason",
                    "question_text": by_id["arrival_reason"]["question"],
                    "answer_source": "custom",
                    "answer_text": "I came to trace my mentor's stolen signal mirror",
                    "character_id": _character_id,
                    "session_id": session_id,
                },
                {
                    "question_id": "personal_stake",
                    "option_id": by_id["personal_stake"]["options"][0]["id"],
                    "answer_source": "user_choice",
                    "answer_text": by_id["personal_stake"]["options"][0]["value"],
                },
                {
                    "question_id": "followed_complication",
                    "option_id": "ai_choose",
                    "answer_source": "ai_choice",
                },
                {
                    "question_id": "npc_connection",
                    "custom_value": "Harbormaster Vell still owes me a quiet favor",
                },
            ],
        },
    )
    assert submit.status_code == 200, submit.text
    anchor = submit.json()["anchors"][0]
    assert anchor["source"] == "player_answered"
    assert anchor["arrival_reason"] == "I came to trace my mentor's stolen signal mirror"
    assert anchor["personal_stake"] == by_id["personal_stake"]["options"][0]["value"]
    assert anchor["followed_complication"]
    assert anchor["known_npc_connection"] == "Harbormaster Vell still owes me a quiet favor"
    bridge_answers = submit.json()["opening_setup"]["bridge_answers"]
    assert len(bridge_answers) >= 4
    by_answer_id = {answer["question_id"]: answer for answer in bridge_answers}
    assert by_answer_id["arrival_reason"] == {
        "question_id": "arrival_reason",
        "question_text": by_id["arrival_reason"]["question"],
        "answer_source": "custom",
        "answer_text": "I came to trace my mentor's stolen signal mirror",
        "character_id": str(_character_id),
        "campaign_id": by_answer_id["arrival_reason"]["campaign_id"],
        "session_id": session_id,
    }
    assert by_answer_id["personal_stake"]["answer_source"] == "user_choice"
    assert by_answer_id["personal_stake"]["answer_text"] == by_id["personal_stake"]["options"][0]["value"]
    assert by_answer_id["followed_complication"]["answer_source"] == "ai_choice"
    assert by_answer_id["followed_complication"]["answer_text"]
    assert by_answer_id["npc_connection"]["answer_source"] == "custom"
    assert by_answer_id["npc_connection"]["answer_text"] == "Harbormaster Vell still owes me a quiet favor"

    saved = json.loads((Path(sessions_module.BASE) / session_id / "opening_character_anchors.json").read_text())
    assert saved[0]["arrival_reason"] == anchor["arrival_reason"]
    saved_meta = client.get(f"/sessions/{session_id}/meta", headers=_auth(email)).json()
    assert saved_meta["session_start_context"]["answers"]["arrival_reason"] == anchor["arrival_reason"]
    assert saved_meta["session_start_context"]["bridge_answers"] == bridge_answers
    assert saved_meta["session_start_context"]["campaign_brief"] == campaign_brief


def test_provisional_character_anchor_naturalizes_class_and_validates_brief():
    seed = {
        "starting_location": "Cinder Vote Hall",
        "location_identity": "Cinder Vote Hall is a heat-stained assembly chamber built over old volcanic vents.",
        "first_clue_or_question": "Who is lying?",
        "specific_stakes": "If the count is certified tonight, the charter becomes law.",
        "inciting_event": "A sealed cinder relic has cracked open before the vote is certified.",
    }
    character = {"id": 77, "name": "Bastog", "level": 5, "class_name": "Warlock / Paladin", "sheet": {}}

    anchor = generate_provisional_character_anchor(character=character, premise=seed)
    knowledge = naturalizeCharacterKnowledge(character, {**seed, "object_name": "broken seal"}, anchor)
    assert set(anchor) == {
        "public_identity",
        "private_tension",
        "reason_to_care",
        "known_connection_to_starting_problem",
        "class_flavor_translation",
    }
    assert "Warlock / Paladin" not in json.dumps(anchor)
    assert "As a" not in knowledge
    assert "oath" in knowledge.lower()
    assert "pact" in knowledge.lower()

    brief = build_campaign_brief(
        campaign={"campaign_name": "Relics of the Void", "campaign_pitch": "Guild factions fight over a miners' charter."},
        character=character,
        opening_seed=seed,
    )
    brief_blob = json.dumps(brief).lower()
    validation = validate_campaign_brief(brief)
    assert validation["valid"], validation
    assert "cinder vote hall" in brief_blob
    assert "cinder relic" in brief_blob or "broken seal" in brief_blob
    assert "guild factions" in brief_blob
    assert "as a warlock" not in brief_blob
    assert "before the truth is public" not in brief_blob


def test_ai_setup_builds_one_coherent_answer_set_instead_of_picking_first_options(monkeypatch):
    questionnaire = {
        "campaign_brief": {
            "title": "Ashes of the Fallen Throne",
            "location_name": "Royal Crypt of Varyn",
            "known_facts": [
                "The dead king's signet was found in a rebel camp.",
                "The public funeral is already underway.",
            ],
            "brief_paragraphs": [
                "The succession is disputed after the dead king's signet surfaced in a rebel camp.",
            ],
        },
        "questions": [
            {
                "id": "arrival_reason",
                "question": "What brought Yungmin here?",
                "options": [
                    {"id": "study", "value": "Study an urn before it is hidden"},
                    {"id": "escort", "value": "Escort someone through the crypt"},
                ],
            },
            {
                "id": "personal_stake",
                "question": "Why does this matter?",
                "options": [
                    {"id": "person", "value": "Someone I care about could be exposed"},
                ],
            },
            {
                "id": "followed_complication",
                "question": "What followed you here?",
                "options": [
                    {"id": "debt", "value": "A debt collector is close behind"},
                ],
            },
        ],
    }
    generated = {
        "arrival_reason": "I came to see whether the signet displayed at the funeral matches the one found in the rebel camp.",
        "personal_stake": "If the signet is genuine, choosing a side before I understand it could help crown the wrong claimant.",
        "followed_complication": "Nothing followed me here; the disputed signet is the problem I am dealing with.",
    }
    monkeypatch.setattr(
        opening_setup_module,
        "chat_complete",
        lambda *args, **kwargs: json.dumps(generated),
    )

    answers = auto_generate_answers(
        questionnaire=questionnaire,
        character={"name": "Yungmin", "class_name": "Wizard", "sheet": {}},
    )

    assert {answer["question_id"]: answer["answer_text"] for answer in answers} == generated
    assert all(answer["answer_source"] == "ai_choice" for answer in answers)
    blob = json.dumps(answers).lower()
    assert "debt collector" not in blob
    assert "someone i care about" not in blob


def test_ai_setup_fallback_does_not_invent_personal_history(monkeypatch):
    questionnaire = {
        "campaign_brief": {
            "title": "Ashes of the Fallen Throne",
            "location_name": "Royal Crypt of Varyn",
            "known_facts": [
                "The succession is disputed.",
                "The dead king's signet is the clearest physical evidence.",
            ],
            "brief_paragraphs": [],
        },
        "questions": [
            {"id": "arrival_reason", "question": "Why are you here?", "options": [{"id": "debt", "value": "Repay an old debt"}]},
            {"id": "personal_stake", "question": "Why care?", "options": [{"id": "family", "value": "Protect my sister"}]},
            {"id": "followed_complication", "question": "What followed?", "options": [{"id": "rival", "value": "A rival followed me"}]},
            {"id": "npc_connection", "question": "Who do you know?", "options": [{"id": "friend", "value": "The regent once helped me"}]},
        ],
    }
    monkeypatch.setattr(opening_setup_module, "chat_complete", lambda *args, **kwargs: None)

    answers = auto_generate_answers(questionnaire=questionnaire, character={"name": "Yungmin"})
    blob = json.dumps(answers).lower()

    assert len(answers) == 4
    assert all(answer["answer_source"] == "ai_choice" for answer in answers)
    for unsupported in ("old debt", "my sister", "a rival followed", "once helped me"):
        assert unsupported not in blob
    assert "no extra complication" in blob
    assert "no one here has an assumed history" in blob


def test_ai_setup_rejects_ungrounded_history_and_non_object_json(monkeypatch):
    questionnaire = {
        "campaign_brief": {
            "title": "Ashes of the Fallen Throne",
            "location_name": "Royal Crypt of Varyn",
            "known_facts": ["The public funeral is underway.", "The dead king's signet was found in a rebel camp."],
            "brief_paragraphs": [],
        },
        "questions": [
            {
                "id": "arrival_reason",
                "question": "What brought you here?",
                "options": [{"id": "debt", "value": "My sister is being pursued by debt collectors."}],
            },
            {
                "id": "npc_connection",
                "question": "Who do you know here?",
                "options": [{"id": "friend", "value": "Captain Vell is an old friend."}],
            },
        ],
    }
    monkeypatch.setattr(
        opening_setup_module,
        "chat_complete",
        lambda *args, **kwargs: json.dumps(
            {
                "arrival_reason": "I came because my sister is being pursued by debt collectors.",
                "npc_connection": "I already trust Captain Vell, an old friend from the royal crypt.",
            }
        ),
    )

    answers = auto_generate_answers(questionnaire=questionnaire, character={"name": "Yungmin"})

    assert answers[0]["answer_text"] == opening_setup_module._safe_auto_answer(
        questionnaire["questions"][0], questionnaire
    )
    assert "sister" not in answers[0]["answer_text"].lower()
    assert answers[1]["answer_text"] == opening_setup_module._safe_auto_answer(
        questionnaire["questions"][1], questionnaire
    )
    assert "captain vell" not in answers[1]["answer_text"].lower()
    assert opening_setup_module._is_grounded_ai_answer(
        "I came because my sister is being pursued by debt collectors.",
        questionnaire,
        {"backstory": "My sister is being pursued by debt collectors."},
    )
    for malformed in ('[{"arrival_reason": "not an object root"}]', '"answer"', "7", "null"):
        assert opening_setup_module._parse_ai_setup_answers(malformed, {"arrival_reason"}) == {}


def test_skip_generates_anchor_and_party_questionnaire_includes_bond():
    client = _client()
    owner = "opening-party@example.com"
    _ensure_user(owner)
    campaign = db.create_campaign(
        owner_id=db.get_user_by_identifier(owner).id,
        name="Party Opening",
        description="A caravan mystery at a moonlit river crossing.",
    )
    sid, _meta = sessions_module.create_session_folder(
        "Party Opening",
        owner,
        campaign_id=campaign.id,
        opening_setup_required=True,
    )

    setup = client.get(f"/sessions/{sid}/opening-setup", headers=_auth(owner))
    assert setup.status_code == 200, setup.text
    questions = setup.json()["questionnaire"]["questions"]
    assert any(question["id"] == "party_bond" for question in questions)

    skipped = client.post(f"/sessions/{sid}/opening-setup/skip", headers=_auth(owner))
    assert skipped.status_code == 200, skipped.text
    anchor = skipped.json()["anchors"][0]
    assert anchor["source"] == "auto_generated"
    assert anchor["party_bond"]
    assert skipped.json()["opening_setup"]["completed"] is True
    assert skipped.json()["opening_setup"]["campaign_brief"]
    bridge_answers = skipped.json()["opening_setup"]["bridge_answers"]
    assert bridge_answers
    assert all(answer["answer_source"] == "ai_choice" for answer in bridge_answers)
    assert {answer["question_id"] for answer in bridge_answers} == {question["id"] for question in questions}


def test_skip_stores_edited_character_hook_in_session_start_context():
    client = _client()
    email = "opening-hook-override@example.com"
    session_id, _character_id = _create_campaign_session(client, email, "Bastog")

    setup = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email))
    assert setup.status_code == 200, setup.text
    hook = "Bastog's oath and patron both react to the cracked signal mirror, but they demand different answers."
    skipped = client.post(
        f"/sessions/{session_id}/opening-setup/skip",
        headers=_auth(email),
        json={"character_hook_override": hook},
    )
    assert skipped.status_code == 200, skipped.text
    anchor = skipped.json()["anchors"][0]
    assert anchor["personal_stake"] == hook
    assert hook in anchor["must_include"]

    saved_meta = client.get(f"/sessions/{session_id}/meta", headers=_auth(email)).json()
    context = saved_meta["session_start_context"]
    assert context["character_hook_override"] == hook
    assert context["answers"]["character_hook_override"] == hook
    assert context["campaign_brief"]["character_anchor"]["reason_to_care"] == hook


def test_start_after_opening_setup_includes_anchor_and_debug_context(monkeypatch):
    client = _client()
    email = "opening-start-anchor@example.com"
    session_id, _character_id = _create_campaign_session(client, email, "Maris Vale")

    monkeypatch.setattr(
        sessions_module.image_agent,
        "generate_image",
        lambda request: type("ImageResult", (), {"image_url": None})(),
    )

    setup = client.get(f"/sessions/{session_id}/opening-setup", headers=_auth(email)).json()["questionnaire"]
    submit = client.post(
        f"/sessions/{session_id}/opening-setup",
        headers=_auth(email),
        json={
            "questionnaire_id": setup["questionnaire_id"],
            "answers": [
                {"question_id": "arrival_reason", "custom_value": "I came to audit a cracked signal mirror"},
                {"question_id": "personal_stake", "custom_value": "My sister vanished after recording this same mirror flaw"},
                {"question_id": "npc_connection", "custom_value": "Archivist Renn knows I can read mirror-cant"},
            ],
        },
    )
    assert submit.status_code == 200, submit.text

    start = client.post(f"/sessions/{session_id}/start", headers=_auth(email), json={})
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["ok"] is True
    scene = body["scene"]
    text = scene["text"].lower()
    assert "maris vale" in text
    assert "cracked signal mirror" in text
    assert "sister vanished" in text or "mirror-cant" in text
    assert scene["anchor_validation"]["valid"] is True
    assert scene["first_scene_validation"]["valid"] is True
    assert scene["opening_character_anchor"]["character_name"] == "Maris Vale"
    assert scene["opening_bundle_context"]["arrival_reason"] == "I came to audit a cracked signal mirror"
    assert scene["opening_setup"]["campaign_brief"]
    assert scene["opening_scene_validation"]["valid"] is True
    opening_scene = scene["opening_scene"]
    assert {
        "scene_title",
        "location_name",
        "time_of_day",
        "opening_narrative",
        "visible_problem",
        "personal_hook",
        "named_npcs",
        "key_objects_or_clues",
        "pressure_or_timer",
        "action_options",
    }.issubset(opening_scene)
    assert len(opening_scene["action_options"]) >= 3
    assert len(scene["choices"]) >= 3
    assert all("Scout ahead cautiously" != choice["label"] for choice in scene["choices"])
    assert all("Press forward decisively" != choice["label"] for choice in scene["choices"])
    assert any(
        any(token.lower() in choice["label"].lower() for token in opening_scene["key_objects_or_clues"] + opening_scene["named_npcs"])
        for choice in scene["choices"]
    )
    assert scene["quality_debug"]["anchor_validation"]["valid"] is True
    assert scene["quality_debug"]["first_scene_validation"]["valid"] is True


def test_campaign_brief_naturalizes_raw_questions_and_contextualizes_questions():
    seed = {
        "starting_location": "Thornwatch Pass",
        "first_clue_or_question": "Who is lying?",
        "specific_stakes": "At dusk, the pass wardens lock the north gate.",
        "named_npc_or_visible_threat": "Warden Hale (refuge keeper)",
    }
    character = {"id": 99, "name": "Yungmin", "class_name": "Wizard", "backstory": "A scholar of border omens."}
    brief = build_campaign_brief(
        campaign={"campaign_name": "The Amber Throne"},
        character=character,
        opening_seed=seed,
    )
    brief_blob = json.dumps(brief).lower()
    assert "who is lying?" not in brief_blob
    for placeholder in (
        "covered clue",
        "first useful evidence",
        "same pressure",
        "practical reason",
        "someone is lying",
        "concrete clue",
        "visible clue",
        "if no one acts soon",
    ):
        assert placeholder not in brief_blob
    assert "different accounts" in brief_blob or "official account is false" in brief_blob
    assert "as a wizard" not in brief_blob
    assert brief["title"] == "The Amber Throne"
    assert brief["location_name"] == "Thornwatch Pass"
    assert "Yungmin arrives before the truth is known" in brief["character_entry_prompt"]

    questionnaire = generate_questionnaire(
        session_id="brief-test",
        campaign_id="1",
        campaign_contract={"campaign_name": "The Amber Throne"},
        opening_seed=seed,
        character=character,
    )
    blob = json.dumps(questionnaire).lower()
    assert "who is lying?" not in blob
    arrival = next(q for q in questionnaire["questions"] if q["id"] == "arrival_reason")
    assert arrival["question"] == "What brought Yungmin here?"
    assert "three witnesses contradict each other" in arrival["helper_text"].lower()
    assert any("thornwatch pass" in option["label"].lower() for option in arrival["options"])


def test_opening_scene_contract_rejects_generic_approach_buttons_and_accepts_grounded_scene():
    required = {
        "starting_location": "Greywood Market",
        "first_clue_or_question": "Who is lying?",
        "specific_stakes": "If no one acts, the lead leaves by dusk.",
        "named_npc_or_visible_threat": "Warden Hale (watch captain)",
        "inciting_event": "A chapel reliquary appears on a fishmonger's table.",
    }
    anchor = {
        "character_name": "Bastog",
        "arrival_reason": "I came to inspect chapel marks on the cloth",
        "personal_stake": "my oath depends on proving the relic was moved",
    }
    brief = build_campaign_brief(
        campaign={"campaign_name": "The Amber Throne"},
        character={"name": "Bastog", "class_name": "Warlock / Paladin"},
        opening_seed=required,
    )
    opening = build_opening_scene_contract(
        required=required,
        anchor=anchor,
        campaign_brief=brief,
        player_name="Bastog",
        time_of_day="noon",
    )
    scene = {
        "text": f"{opening['opening_narrative']}\n\nWhat does Bastog do?",
        "narrative_body": opening["opening_narrative"],
        "location": opening["location_name"],
        "choices": [{"id": str(i), "label": label} for i, label in enumerate(opening["action_options"])],
    }
    valid = validate_opening_scene_contract(
        scene=scene,
        opening_scene=opening,
        campaign_brief=brief,
        anchor=anchor,
        player_name="Bastog",
    )
    assert valid["valid"] is True
    assert "Bastog" in opening["opening_narrative"]
    assert "Greywood Market" in opening["opening_narrative"]
    assert any("reliquary" in option.lower() for option in opening["action_options"])

    bad = validate_opening_scene_contract(
        scene={
            "text": "Your adventure begins. Choose an approach to set the tone.",
            "location": "Greywood Market",
            "choices": [
                {"id": "scout", "label": "Scout ahead cautiously"},
                {"id": "parley", "label": "Seek conversation first"},
                {"id": "press", "label": "Press forward decisively"},
            ],
        },
        opening_scene=opening,
        campaign_brief=brief,
        anchor=anchor,
        player_name="Bastog",
    )
    assert bad["valid"] is False
    assert any("generic" in issue.lower() or "grounded" in issue.lower() for issue in bad["issues"])


def test_opening_anchor_validator_rejects_wrong_name_and_missing_anchor_content():
    anchor = {
        "character_name": "Correct Hero",
        "arrival_reason": "I came to recover the brass writ",
        "pre_scene_activity": "was already trying to recover the brass writ",
        "personal_stake": "My oath depends on the brass writ being found",
    }
    result = validate_opening_anchor(
        scene_text="Wrong Hero watches a generic argument at the gate.",
        anchor=anchor,
        selected_character_name="Correct Hero",
        known_character_names=["Wrong Hero", "Correct Hero"],
    )
    assert result["valid"] is False
    assert any("Selected character" in issue for issue in result["issues"])
    assert any("fewer than two anchor" in issue for issue in result["issues"])
    assert any("Stale character name" in issue for issue in result["issues"])


def test_first_scene_contract_rejects_meta_language_and_unjustified_rolls():
    anchor = {
        "character_name": "Correct Hero",
        "arrival_reason": "I came to recover the brass writ",
        "pre_scene_activity": "was already trying to recover the brass writ",
        "personal_stake": "My oath depends on the brass writ being found",
    }
    scene = {
        "text": (
            "Correct Hero stands at the gate. The story plan says the scene should start here. "
            "The first witness waits. A underground door opens."
        ),
        "choices": [{"label": "Look"}],
    }
    result = validate_first_scene_contract(
        scene=scene,
        anchor=anchor,
        player_name="Correct Hero",
        dice_rolls=[{"skill": "Persuasion", "type": "d20", "reason": "generic persuasion default"}],
    )
    assert result["valid"] is False
    assert any("Forbidden first-scene language" in issue for issue in result["issues"])
    assert any("fewer than three" in issue for issue in result["issues"])
    assert any("Dice request" in issue for issue in result["issues"])


# --- Quick Start brief quality (live dashboard review, Oct 6 2026) -------------

def _fantasy_brief(seed_no: int) -> dict:
    from server.agents.content_bundles import generate_starter_seed

    camp = {
        "campaign_name": "Salt, Steel, and Sorcery", "genre": "fantasy",
        "setting_summary": "Magic, monsters, and ancient prophecies.",
        "campaign_pitch": "Magic, monsters, and ancient prophecies.",
    }
    seed = generate_starter_seed({"setting_summary": camp["setting_summary"], "genre": "fantasy"}, seed=seed_no)
    return build_campaign_brief(
        campaign=camp, character={"name": "Arin Quickstep", "class_name": "Rogue", "level": 3}, opening_seed=seed,
    )


def test_quick_start_brief_has_no_splice_duplicates_or_invented_fixtures():
    import re

    for seed_no in range(40):
        brief = _fantasy_brief(seed_no)
        pieces = brief["brief_paragraphs"] + brief["known_facts"]
        text = " ".join(pieces + [brief["character_entry_prompt"]])
        assert not re.search(r"[.!?] [a-z]", text), text  # "...established yet. could settle..."
        assert "the object" not in text and "the room" not in text, text
        assert "public count" not in text and "sealed letter" not in text, text
        sentences = [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+", " ".join(pieces)) if s.strip()]
        assert len(sentences) == len(set(sentences)), sentences  # nothing is shown twice


def test_character_knowledge_is_not_repeated_as_a_known_fact():
    brief = _fantasy_brief(1)
    knowledge = brief["brief_paragraphs"][3]
    assert not any(knowledge[:40] in fact for fact in brief["known_facts"] + brief["provisional_facts"])
    reason = brief["character_anchor"].get("reason_to_care", "")
    assert reason and reason not in knowledge  # the reason has its own box in the UI


def test_consequence_never_splices_a_sentence_before_could_settle():
    from server.agents.opening_setup import UNKNOWN_AUTHORITY, _visible_consequence

    seed = {"specific_stakes": "?"}  # unusable stakes force the generic consequence
    assert _visible_consequence(seed, {}, UNKNOWN_AUTHORITY).startswith("Whoever holds authority here could settle")
    real = _visible_consequence(seed, {}, "The harbor office and envoy guard are blaming each other.")
    assert real.startswith("The harbor office and envoy guard could settle"), real


def test_entry_prompt_only_calls_it_a_mystery_for_mystery_campaigns():
    from server.agents.opening_setup import _trouble_noun

    assert _trouble_noun({"genre": "fantasy"}) == "trouble"
    assert _trouble_noun({"campaign_dna": {"genre": "horror"}}) == "trouble"
    assert _trouble_noun({"genre": "mystery"}) == "mystery"
    assert _trouble_noun({}) == "mystery"  # genre unknown: keep the long-standing wording
    assert "this trouble" in _fantasy_brief(0)["character_entry_prompt"]
