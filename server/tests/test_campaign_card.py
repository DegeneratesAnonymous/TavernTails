import json

from server.agents.campaign_card import (
    OPEN,
    SAID,
    apply_answers,
    card_to_campaign,
    derive_settings,
    is_grounded,
    read_campaign_card,
)

TEXT = (
    "A grim harbor town where the lighthouse keeper Maren Vey vanished. Political, not much combat. "
    "5e, level 3. The Tidewardens run the docks. Please avoid harm to children."
)


def _answer(**overrides):
    data = {
        "name": "The Dark Lamp",
        "premise": "A grim harbor town where the lighthouse keeper vanished",
        "genre": "political",
        "tone": "grim",
        "world_name": "",
        "starting_place": "The Drowned Lighthouse",
        "opening_trouble": "",
        "ruleset": "D&D 5e",
        "starting_level": 3,
        "pacing": "slow",
        "content_rating": "pg-13",
        "ai_freedom": "medium",
        "people": [{"name": "Maren Vey", "role": "keeper"}, {"name": "Captain Orlo", "role": "smuggler"}],
        "factions": ["Tidewardens", "Salt Syndicate"],
        "themes": ["corruption"],
        "content_limits": ["harm to children"],
        "open_questions": ["Who profits from the dark lamp?", "not a question"],
    }
    data.update(overrides)
    return lambda *a, **k: json.dumps(data)


def test_said_guessed_and_open_are_decided_against_the_players_text():
    card = read_campaign_card(TEXT, complete=_answer())
    fields = card["fields"]
    assert fields["premise"]["status"] == SAID
    assert fields["tone"] == {"value": "grim", "status": SAID}
    assert fields["starting_level"] == {"value": 3, "status": SAID}
    assert fields["ruleset"] == {"value": "D&D 5e", "status": SAID}
    assert fields["name"]["status"] == "guessed"
    assert fields["pacing"]["status"] == "guessed"
    # A place the player never wrote is not shown as a fact.
    assert fields["starting_place"]["status"] == OPEN
    assert card["diagnostics"] == {"source": "model"}


def test_invented_people_and_factions_are_dropped():
    card = read_campaign_card(TEXT, complete=_answer())
    assert [p["name"] for p in card["people"]] == ["Maren Vey"]
    assert [f["name"] for f in card["factions"]] == ["Tidewardens"]
    assert card["content_limits"] == ["harm to children"]
    assert card["open_questions"] == ["Who profits from the dark lamp?"]


def test_follow_ups_only_ask_for_what_blocks_the_first_scene():
    card = read_campaign_card(TEXT, complete=_answer())
    assert [q["field"] for q in card["follow_ups"]] == ["starting_place", "opening_trouble"]
    grounded = read_campaign_card(
        TEXT + " It opens at the Gull Steps, where a ship is overdue.",
        complete=_answer(starting_place="the Gull Steps", opening_trouble="a ship is overdue"),
    )
    assert grounded["follow_ups"] == []


def test_the_genre_button_beats_the_models_guess():
    card = read_campaign_card("Ghosts in the old mill.", starter={"genre": "horror"}, complete=_answer(genre="fantasy"))
    assert card["fields"]["genre"] == {"value": "horror", "status": SAID}


def test_model_failure_still_returns_a_usable_card():
    def boom(*a, **k):
        raise TimeoutError

    card = read_campaign_card(TEXT, starter={"genre": "mystery"}, complete=boom)
    assert card["diagnostics"]["source"] == "fallback"
    assert card["fields"]["premise"]["status"] == SAID
    assert card["fields"]["genre"] == {"value": "mystery", "status": SAID}
    assert card["fields"]["starting_level"]["value"] == 3
    assert card["fields"]["ruleset"]["value"] == "D&D 5e"
    unparseable = read_campaign_card(TEXT, complete=lambda *a, **k: "no json here")
    assert unparseable["diagnostics"] == {"source": "fallback", "reason": "unparseable"}


def test_freedom_decides_canon_and_creativity():
    card = read_campaign_card("Surprise me with a weird sky-island heist.", complete=_answer(ai_freedom="high"))
    assert derive_settings(card) == {
        "canon_policy": "flexible_canon", "ai_creativity_level": "expansive", "creation_posture": "player_fast_start",
    }
    strict = read_campaign_card(TEXT, lore="Lore " * 50, complete=_answer(ai_freedom="low"))
    assert strict["derived"] == {
        "canon_policy": "strict_canon", "ai_creativity_level": "conservative", "creation_posture": "lore_importer",
    }


def test_card_becomes_campaign_settings_with_answers_as_the_players_words():
    card = apply_answers(read_campaign_card(TEXT, complete=_answer()), {
        "starting_place": "the Gull Steps",
        "opening_trouble": "The lamp went dark and a ship is overdue",
        "not_a_follow_up": "ignored",
    })
    assert card["fields"]["starting_place"] == {"value": "the Gull Steps", "status": SAID}
    values = card_to_campaign(card)
    settings = values["settings"]
    assert settings["starting_location"] == "the Gull Steps"
    assert settings["setting_summary"].startswith(TEXT.rstrip("."))
    assert settings["setting_summary"].endswith("The lamp went dark and a ship is overdue.")
    assert settings["genre"] == "political" and settings["starting_level"] == 3
    assert settings["content_limits"] == ["harm to children"]
    assert values["variables"]["factions"] == [{"name": "Tidewardens"}]
    assert values["name"] == "The Dark Lamp"


def test_open_fields_stay_out_of_settings():
    values = card_to_campaign(read_campaign_card(TEXT, complete=_answer()))
    assert "starting_location" not in values["settings"]
    assert "opening_trouble" not in values["settings"]
    assert values["settings"]["world_name"] == ""


def test_grounding_needs_most_content_words():
    source = "The lighthouse keeper vanished from the harbor"
    assert is_grounded("lighthouse keeper vanished", source)
    assert not is_grounded("The Drowned Lighthouse of Saltmere", source)
    assert not is_grounded("", source)


def test_the_whole_advertised_description_is_kept():
    text = ("The harbor keeps its secrets. " * 260)[:7900]
    card = read_campaign_card(text, complete=lambda *a, **k: None)
    assert card["text"] == text.strip()


def test_names_match_as_whole_words():
    from server.agents.campaign_card import name_in_text

    assert name_in_text("Maren Vey", "the keeper maren vey vanished")
    assert not name_in_text("Art Bell", "artifacts and Belladonna")
    assert not name_in_text("Vey", "surveyors")


def test_an_edited_premise_leads_the_summary_the_world_is_built_from():
    card = read_campaign_card(TEXT, complete=_answer())
    editable = {**card, "fields": {**card["fields"], "premise": {"value": "A cozy fishing village festival gone wrong", "status": "said"}}}
    summary = card_to_campaign(editable)["settings"]["setting_summary"]
    assert summary.startswith("A cozy fishing village festival gone wrong.")
    assert card_to_campaign(card)["settings"]["setting_summary"].startswith("A grim harbor town")


def test_rating_and_limits_reach_the_contract_safety_policy():
    from fastapi.testclient import TestClient

    import server.main as main
    from server import db
    from server.auth import create_access_token

    email = "card-safety@example.com"
    user = db.get_user_by_identifier(email) or db.create_user(email=email, password="secret", username="cardsafety")
    if not user.verified:
        db.verify_user(email, user.verification_token or "")
    card = read_campaign_card(TEXT, complete=_answer(content_rating="family"))
    res = TestClient(main.app).post(
        "/campaigns",
        headers={"Authorization": f"Bearer {create_access_token(email)}"},
        json={"name": "Safe", "card": card, "create_session": False, "generate_world": False},
    )
    assert res.status_code == 201, res.text
    contract = db.get_campaign_by_id(res.json()["campaign"]["id"]).metadata_json["campaign_contract"]
    assert contract["safety_policy"]["content_rating"] == "family"
    assert contract["safety_policy"]["avoid"] == ["harm to children"]


def test_a_role_the_text_does_not_give_is_dropped():
    card = read_campaign_card(TEXT, complete=_answer(people=[{"name": "Maren Vey", "role": "smuggler queen"}]))
    assert card["people"] == [{"name": "Maren Vey", "role": "", "status": "said"}]
    kept = read_campaign_card(TEXT, complete=_answer(people=[{"name": "Maren Vey", "role": "lighthouse keeper"}]))
    assert kept["people"][0]["role"] == "lighthouse keeper"
