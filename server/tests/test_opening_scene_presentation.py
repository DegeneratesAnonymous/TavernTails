"""The opening scene reads as one scene: restated setup answers, one written-whole draft, no menus in prose."""
import json

import pytest

from server import steward_llm
from server.agents import scene_weaver, sessions
from server.agents.opening_setup import UNNAMED_WITNESS, build_opening_scene_contract
from server.agents.opening_voice import anchor_sentences, first_to_third, usable_answer
from server.agents.scene_qa import apply_targeted_scene_repairs

REQUIRED = {
    "starting_location": "Greywood Market",
    "location_identity": "Greywood Market is a crowded square beneath old chapel bells.",
    "first_clue_or_question": "Who moved the reliquary?",
    "specific_stakes": "If no one acts, the reliquary leaves by dusk.",
    "named_npc_or_visible_threat": "Mara Voss (watch captain)",
    "inciting_event": "A chapel reliquary appears on a fishmonger's table.",
}
ANCHOR = {"character_name": "Bastog", "arrival_reason": "I came to inspect chapel marks on the cloth",
          "personal_stake": "my oath depends on proving the relic was moved", "source": "player_answered"}

GOOD_DRAFT = (
    "Greywood Market hums beneath the old chapel bells, and the morning is cold enough that breath shows in the air. "
    "Bastog crosses the square, drawn here to inspect the chapel marks that were pressed into a fishmonger's cloth.\n\n"
    "A chapel reliquary sits on that table, and the stallholders keep their eyes on their baskets. "
    "Nobody will touch it, and the smell of salt and old wax hangs over everything.\n\n"
    "A watch captain stands at the edge of the crowd, one hand on her belt and her eyes on the reliquary. "
    "She is Mara Voss, and she has not moved in a long while.\n\n"
    "Bastog's oath rests on showing the relic was carried here from somewhere else, and the cloth is the only proof "
    "within reach. The bells will ring dusk soon, and the reliquary will not be here to see it. "
    "Down the lane a cart wheel creaks and stops."
)


# --- the player's own answers, restated -------------------------------------------------------------------------

def test_first_person_answers_are_restated_with_they_not_quoted():
    assert first_to_third("I do not want the evidence to disappear.") == "they do not want the evidence to disappear."
    assert first_to_third("I'm the one who signed her in; my name is on it.") == "they're the one who signed her in; their name is on it."
    assert first_to_third("The road is closed.") == "The road is closed."  # nothing first-person: unchanged


def test_anchor_sentences_cover_clauses_statements_and_fragments_without_broken_grammar():
    clause = anchor_sentences({"arrival_reason": "I came to inspect the cloth", "personal_stake": "My oath depends on it."}, "Bastog")
    assert clause == ("Bastog did not come by chance: they came to inspect the cloth. "
                      "The reason this matters to Bastog: their oath depends on it.")
    thoughts = anchor_sentences({"arrival_reason": "Who moved the mirror?", "personal_stake": "Never let my sister vanish"}, "Maris")
    assert '"Who moved the mirror?"' in thoughts and '"Never let my sister vanish."' in thoughts
    assert "?." not in thoughts
    statement = anchor_sentences({"arrival_reason": "I came to look", "followed_complication": "A rival is close behind."}, "Maren")
    assert statement.endswith("A rival is close behind.")


def test_anchor_sentences_skip_placeholders_and_null_answers_and_stop_at_two():
    anchor = {"arrival_reason": "I came to look", "personal_stake": "The campaign has not yet decided what ties them here",
              "followed_complication": "No extra complication followed me here.", "fear_of_loss": "I fear losing the trail"}
    text = anchor_sentences(anchor, "Maren")
    assert "has not yet decided" not in text and "complication" not in text.lower()
    assert text.count(":") == 2  # arrival + fear; never a recital of every answer
    assert anchor_sentences({"arrival_reason": "I came here"}, "the party").startswith("The party did not come by chance")
    assert usable_answer("Never let my sister vanish again") == "Never let my sister vanish again"  # "never" is a real stake
    assert anchor_sentences({}, "Maren") == ""


# --- the fallback template ----------------------------------------------------------------------------------------

def test_template_opening_is_one_scene_without_menu_repeat_or_wrong_time_of_day():
    opening = build_opening_scene_contract(required=REQUIRED, anchor=ANCHOR, campaign_brief={}, player_name="Bastog", time_of_day="day")
    body = opening["opening_narrative"]
    assert body.count("arrives") == 1 and "reaches" not in body  # the arrival is stated once
    assert "A watch captain, Mara Voss, stands" in body  # the person is introduced by what they are, then by name
    assert " can " not in body.split("\n\n")[-1] and "or Question" not in body  # no list of options in the story
    assert body.count("?") == 1  # the one unanswered question, stated once
    assert "sinking light" not in body  # it is day: the deadline is in the future
    assert "Bastog did not come by chance: they came to inspect chapel marks on the cloth" in body
    assert len(opening["action_options"]) >= 3  # the options stay as data for the validators and for suggestions


def test_template_still_uses_an_honest_unnamed_witness():
    opening = build_opening_scene_contract(required={"starting_location": "Marrow Gate", "inciting_event": "A bell rings."},
                                           anchor={"character_name": "the party"}, campaign_brief={}, player_name="")
    assert UNNAMED_WITNESS in opening["opening_narrative"]


def test_qa_repair_never_writes_the_options_into_the_player_prompt():
    scene = {"location": "Alderbrook", "narrative_body": "Ada Reed waits.", "player_prompt": "What does Aria do?",
             "suggested_actions": [], "choices": []}
    qa = {"repair_targets": ["suggested_actions"], "truth_table": {"approved_possible_actions": ["inspect the watch", "ask Ada", "leave"]}}
    result = apply_targeted_scene_repairs(scene, qa, player_name="Aria")
    assert result["player_prompt"] == "What does Aria do?"
    assert len(result["choices"]) == 3 and "or something else" not in result["text"]


# --- the scene writer's checks -------------------------------------------------------------------------------------

def _facts(**overrides):
    facts = scene_weaver.build_facts(location="Greywood Market", time_of_day="day", weather="clear", player_name="Bastog",
                                     anchor=ANCHOR, required=REQUIRED)
    facts.update(overrides)
    return facts


def test_a_good_draft_passes_every_check():
    assert scene_weaver.check_woven(GOOD_DRAFT, _facts()) == []


@pytest.mark.parametrize("mutate, expected", [
    (lambda t: t.replace("\n\n", " "), "paragraphs"),
    (lambda t: t + "\n\nWhat does he do?", "question"),
    (lambda t: t + "\n\nBastog can inspect the cloth, question Mara, watch the crowd, or follow the cart.", "could do"),
    (lambda t: t.replace("Bastog", "Aldric"), "Never names Bastog"),
    (lambda t: t.replace("Mara Voss", "the captain"), "Never names Mara Voss"),
    (lambda t: t.replace("morning is cold", "midnight is moonlit"), "night"),
    (lambda t: t + " " + t, "Too long"),
])
def test_draft_problems_are_named_so_the_model_can_fix_them(mutate, expected):
    issues = " | ".join(scene_weaver.check_woven(mutate(GOOD_DRAFT), _facts()))
    assert expected.lower() in issues.lower()


def test_copying_the_players_words_or_the_brief_is_rejected():
    copied = GOOD_DRAFT.replace("Bastog's oath rests on", "my oath depends on proving the relic was moved. Bastog's oath rests on")
    assert "Copies the character's own words" in " ".join(scene_weaver.check_woven(copied, _facts()))
    brief = ["The bells will ring dusk soon, and the reliquary will not be here to see it."]
    assert "already read" in " ".join(scene_weaver.check_woven(GOOD_DRAFT, _facts(brief_sentences=brief)))


def test_the_party_is_a_valid_name_when_no_character_is_selected():
    facts = _facts(player="the party", reason_for_coming="", why_it_matters="", what_they_fear_losing="")
    draft = GOOD_DRAFT.replace("Bastog's", "The party's").replace("Bastog", "The party")
    assert scene_weaver.check_woven(draft, facts) == []


def test_auto_generated_answers_are_not_passed_to_the_writer_as_facts():
    facts = scene_weaver.build_facts(location="X", time_of_day="day", player_name="Ari",
                                     anchor={**ANCHOR, "source": "auto_generated"}, required=REQUIRED)
    assert facts["reason_for_coming"] == "" and facts["why_it_matters"] == ""


# --- writing the scene ----------------------------------------------------------------------------------------------

def test_weave_returns_the_first_draft_that_passes_and_sends_back_what_was_wrong(monkeypatch):
    calls = []

    def fake(messages, **kwargs):
        calls.append(messages)
        return "Too short." if len(calls) == 1 else json.dumps({"narrative": GOOD_DRAFT})

    monkeypatch.setattr(steward_llm, "chat_complete", fake)
    assert scene_weaver.weave_opening(_facts()) == GOOD_DRAFT
    assert len(calls) == 2
    assert "REJECTED" in calls[1][1]["content"] and "Too short" in calls[1][1]["content"]


def test_weave_gives_up_quietly_when_the_model_fails_or_never_passes(monkeypatch):
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: None)
    assert scene_weaver.weave_opening(_facts()) == ""
    monkeypatch.setattr(steward_llm, "chat_complete", lambda *a, **k: "Nope.")
    assert scene_weaver.weave_opening(_facts(), attempts=2) == ""

    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(steward_llm, "chat_complete", boom)
    assert scene_weaver.weave_opening(_facts()) == ""


def test_best_sentence_finds_the_sentence_that_carries_a_fact():
    sentence = scene_weaver.best_sentence(GOOD_DRAFT, "If no one acts, the reliquary leaves by dusk.", "Greywood Market")
    assert "dusk" in sentence and "reliquary" in sentence
    assert scene_weaver.best_sentence(GOOD_DRAFT, "Nothing in common whatsoever", "Greywood Market") == ""


# --- putting it in the pipeline ---------------------------------------------------------------------------------------

def _patched_scene():
    opening = build_opening_scene_contract(required=REQUIRED, anchor=ANCHOR, campaign_brief={}, player_name="Bastog", time_of_day="day")
    body = opening["opening_narrative"]
    return {
        "location": "Greywood Market", "narrative_body": body, "player_prompt": "What does Bastog do?",
        "text": f"{body}\n\nWhat does Bastog do?", "opening_scene": opening,
        "choices": [{"id": f"a{i}", "label": label} for i, label in enumerate(opening["action_options"])],
        "suggested_actions": list(opening["action_options"]), "generation_debug": {"fallback_used": True},
    }


def _compose(scene, monkeypatch, draft, anchor=ANCHOR):
    monkeypatch.setattr(scene_weaver, "weave_opening", lambda facts, **k: draft)
    return sessions._compose_final_opening(scene, required=REQUIRED, opening_anchor=anchor, campaign_brief={},
                                           player_name="Bastog", time_of_day="day", weather="clear", source_intent=None)


def test_a_patched_opening_is_replaced_by_the_scene_written_whole(monkeypatch):
    result = _compose(_patched_scene(), monkeypatch, GOOD_DRAFT)
    assert result["narrative_body"] == GOOD_DRAFT
    assert result["player_prompt"] == "What does Bastog do?" and result["text"].endswith("What does Bastog do?")
    assert result["generation_debug"]["composed_by"] == "scene_weaver"
    assert len(result["choices"]) >= 3  # options kept as data
    assert result["opening_scene_validation"]["valid"]


def test_a_draft_that_fails_an_opening_check_leaves_the_scene_alone(monkeypatch):
    scene = _patched_scene()
    before = scene["narrative_body"]
    no_person = GOOD_DRAFT.replace("Mara Voss", "the captain")
    assert _compose(scene, monkeypatch, no_person)["narrative_body"] == before
    assert _compose(scene, monkeypatch, "")["narrative_body"] == before


def test_an_opening_the_model_wrote_whole_is_not_rewritten(monkeypatch):
    scene = {**_patched_scene(), "generation_debug": {"fallback_used": False}}
    before = scene["narrative_body"]
    assert _compose(scene, monkeypatch, GOOD_DRAFT)["narrative_body"] == before


def test_unwritten_anchor_answers_do_not_block_a_good_scene(monkeypatch):
    generic = {"character_name": "Bastog", "source": "auto_generated", "arrival_reason": "I came to understand what is here",
               "personal_stake": "my oath matters here"}
    draft = GOOD_DRAFT.replace("drawn here to inspect the chapel marks that were pressed into a fishmonger's cloth", "with no one to meet")
    draft = draft.replace("Bastog's oath rests on showing the relic was carried here from somewhere else, and the cloth is the only proof within reach.",
                          "Bastog watches the cloth and says nothing.")
    assert _compose(_patched_scene(), monkeypatch, draft, anchor=generic)["narrative_body"] == draft


def test_the_prompt_is_taken_out_of_the_prose():
    scene = {"narrative_body": "He waits. What does the party do? .\n\nA bell tolls.", "player_prompt": "What does the party do?"}
    cleaned = sessions._strip_prompt_from_body(scene)
    assert cleaned["narrative_body"] == "He waits.\n\nA bell tolls."
    assert sessions._strip_prompt_from_body({"narrative_body": "Nothing to strip.", "player_prompt": "x"})["narrative_body"] == "Nothing to strip."


def test_each_deadline_is_kept_as_it_was_given():
    base = {"starting_location": "Gate", "inciting_event": "A bell rings."}

    def line(stakes, time="day"):
        return build_opening_scene_contract(required={**base, "specific_stakes": stakes}, anchor={}, campaign_brief={},
                                            player_name="Ari", time_of_day=time)["pressure_or_timer"]

    assert line("The gate opens at dawn.").startswith("By dawn")
    assert line("The trail vanishes in an hour.").startswith("Within the hour")
    assert line("The doors lock at dusk.").startswith("By dusk")
    assert "sinking light" in line("The doors lock at dusk.", time="evening")


def test_lowercase_first_person_answers_are_restated_too():
    assert first_to_third("i came to find my sister") == "they came to find their sister"
    assert anchor_sentences({"arrival_reason": "i came to find my sister"}, "Maris") == (
        "Maris did not come by chance: they came to find their sister.")


def test_the_authored_object_fallback_has_no_list_of_options_either():
    required = {"starting_location": "Alderbrook", "approved_object": "stopped brass pocket watch",
                "field_provenance": {"approved_object": "user"}, "inciting_event": "Every clock stopped at breakfast.",
                "first_clue_or_question": "Who wound the watch last?"}
    body = build_opening_scene_contract(required=required, anchor={"character_name": "Ari"}, campaign_brief={}, player_name="Ari")["opening_narrative"]
    assert " can " not in body and "pocket watch" in body


@pytest.mark.parametrize("time, sentence, bad", [
    ("day", "Night has fallen over the market.", True),
    ("day", "Moonlight spills across the stones.", True),
    ("day", "The sun is bright and the day is clear.", False),
    ("night", "Sunshine floods the market.", True),
    ("night", "A single lantern burns in the dark.", False),
])
def test_plain_day_and_night_contradictions_are_rejected(time, sentence, bad):
    draft = GOOD_DRAFT.replace("the morning is cold enough that breath shows in the air", sentence.rstrip("."))
    facts = _facts(time_of_day=time)
    issues = " ".join(scene_weaver.check_woven(draft, facts)).lower()
    assert ("although the scene happens" in issues) is bad


def test_a_night_opening_may_mention_a_deadline_in_the_morning():
    facts = _facts(time_of_day="night", stakes="The gate opens at dawn, in the morning.")
    draft = GOOD_DRAFT.replace("the morning is cold enough that breath shows in the air", "the night is cold enough that breath shows in the air")
    draft = draft.replace("The bells will ring dusk soon", "The gate opens in the morning, and the bells will ring then")
    assert not [i for i in scene_weaver.check_woven(draft, facts) if "daylight" in i]
    assert [i for i in scene_weaver.check_woven(draft.replace("night is cold", "sunshine is warm and the night is cold"), _facts(time_of_day="night")) if "daylight" in i]


def test_a_confirmed_object_must_survive_the_rewrite_but_a_generated_one_need_not():
    confirmed = {**REQUIRED, "approved_object": "silver reliquary", "field_provenance": {"approved_object": "user"}}
    facts = scene_weaver.build_facts(location="Greywood Market", time_of_day="day", player_name="Bastog", anchor=ANCHOR, required=confirmed)
    assert "Never shows the established silver reliquary" in " ".join(scene_weaver.check_woven(GOOD_DRAFT, facts))
    with_it = GOOD_DRAFT.replace("A chapel reliquary sits on that table", "A silver reliquary sits on that table")
    assert not [i for i in scene_weaver.check_woven(with_it, facts) if "established" in i]
    generated = {**confirmed, "field_provenance": {"approved_object": "generated"}}
    facts = scene_weaver.build_facts(location="Greywood Market", time_of_day="day", player_name="Bastog", anchor=ANCHOR, required=generated)
    assert not [i for i in scene_weaver.check_woven(GOOD_DRAFT, facts) if "established" in i]


@pytest.mark.parametrize("weather, sentence, bad", [
    ("clear", "Rain hammers the awnings.", True),
    ("clear", "The sky is clear and the awnings stand still.", False),
    ("rain", "A clear sky stretches over the square.", True),
    ("rain", "Rain drums on the awnings.", False),
])
def test_the_weather_in_the_story_matches_the_weather_of_the_scene(weather, sentence, bad):
    draft = GOOD_DRAFT.replace("the morning is cold enough that breath shows in the air", sentence.rstrip("."))
    issues = " ".join(scene_weaver.check_woven(draft, _facts(weather=weather)))
    assert ("although the weather is" in issues) is bad


def test_short_canned_answers_count_together_so_a_good_scene_is_not_rejected():
    facts = _facts(reason_for_coming="Study first sign of trouble before it is hidden", why_it_matters="",
                   what_they_fear_losing="A person who still believes in me")
    draft = GOOD_DRAFT.replace("Bastog's oath rests on showing the relic was carried here from somewhere else, and the cloth is the only proof within reach.",
                               "Bastog has come to study the first sign of trouble before anyone hides it, and fears losing the one person who believes in them.")
    assert not [i for i in scene_weaver.check_woven(draft, facts) if "Never says why" in i]
    bare = " ".join(scene_weaver.check_woven(GOOD_DRAFT, facts))
    assert "Never says why" in bare and "Study first sign of trouble" in bare  # and the retry is told what to include


def test_generated_reason_to_care_lines_are_never_narrated_as_the_players_own():
    canned = "Arin Quickstep has useful skills for asking who handled the first sign of trouble, how it moved, and who had access."
    assert usable_answer(canned) == ""
    assert usable_answer("Never let my sister vanish again") != ""


def test_a_role_that_is_capitalised_like_a_title_reads_as_a_role():
    opening = build_opening_scene_contract(required={**REQUIRED, "named_npc_or_visible_threat": "Callum Grieve (Last Patient)"},
                                           anchor={}, campaign_brief={}, player_name="Ari")
    assert "A last patient, Callum Grieve, stands" in opening["opening_narrative"]


def test_two_seats_with_the_same_character_name_are_a_party(tmp_path):
    from server.agents import sessions

    meta = {"members": [{"email": "a@x", "character_id": 1, "character_name": "Mira"}, {"email": "b@x", "character_id": 2, "character_name": "Mira"}]}
    assert sessions._is_party(tmp_path, meta, {"id": 1}) is True
    assert sessions._is_party(tmp_path, {"members": [{"email": "a@x", "character_id": 1, "character_name": "Mira"}]}, {"id": 1}) is False
